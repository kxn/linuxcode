// Linux backend for the legacy /dev/fsevents ABI. The wire layout is derived
// from XNU bsd/sys/fsevents.h and copy_out_kfse() in bsd/vfs/vfs_fsevents.c.
// This first backend supports delete/rename watchers (CoreServices' request).
// It refuses other event selections. inotify has no originating PID; records
// explicitly use PID 0, and incomplete observations produce EVENTS_DROPPED.
#include <darlingserver/fsevents-device.hpp>
#include <darlingserver/fsevents-journal.hpp>

#include <sys/inotify.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <sys/un.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <cstdio>
#include <deque>
#include <filesystem>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <unordered_set>

namespace DarlingServer::FSEvents {
namespace {
namespace fs = std::filesystem;
constexpr int Delete=1, Rename=3, Dropped=999;
constexpr uint16_t String=2, Int64=5, Inode=7, Uid=8, Dev=9, Mode=10, Gid=11, Finfo=12, Done=0xb33f;
constexpr uint32_t Mask=IN_CREATE|IN_DELETE|IN_MOVED_FROM|IN_MOVED_TO|IN_DELETE_SELF|IN_MOVE_SELF|IN_UNMOUNT;
constexpr size_t MaxEntries=2000000;
struct Info { uint64_t inode; uint32_t dev,mode,uid,gid; };
struct Entry { std::string host,guest; Info info; };
struct Pending { Entry entry; std::chrono::steady_clock::time_point time; };
struct Device;
struct Registry {
    std::mutex mutex;
    std::unordered_map<ino_t,std::weak_ptr<Device>> devices;
    std::atomic<uint64_t> serial{1};
};
// Kept alive until process exit; detached workers can finish while globals in
// the rest of darlingserver are being torn down.
Registry& registry() { static auto* value=new Registry; return *value; }
template<class T> void append(std::vector<uint8_t>& bytes,T value) {
    auto* p=reinterpret_cast<const uint8_t*>(&value);bytes.insert(bytes.end(),p,p+sizeof value);
}
template<class T> void arg(std::vector<uint8_t>& bytes,uint16_t type,T value) {
    append(bytes,type);append(bytes,uint16_t(sizeof value));append(bytes,value);
}
bool beneath(const std::string& name,const std::string& parent) {
    return name==parent || (name.size()>parent.size() && name.compare(0,parent.size(),parent)==0 && name[parent.size()]=='/');
}
bool infoFor(const std::string& path,Info& info) {
    struct stat st;
    if (lstat(path.c_str(),&st)<0) return false;
    // This is the same Linux dev_t narrowing used by Darling's stat converter.
    info={uint64_t(st.st_ino),uint32_t(st.st_dev),uint32_t(st.st_mode),st.st_uid,st.st_gid};
    return true;
}
struct Device : std::enable_shared_from_this<Device> {
    int peer=-1,notify=-1;
    ino_t key=0;
    std::vector<Root> roots;
    std::vector<int8_t> actions;
    unsigned depth=0;
    std::mutex mutex;
    bool compact=false,extended=false,filtered=false;
    std::unordered_set<uint32_t> filter;
    std::unordered_map<int,Entry> watches;
    std::unordered_map<std::string,Entry> entries;
    std::unordered_map<uint32_t,Pending> moves;
    std::deque<std::vector<uint8_t>> queue;
    bool lost=false;
    std::vector<Root> journalRoots;
    Journal* journal=nullptr;
    uint64_t subscription=0;
    ~Device() {
        if (notify>=0) close(notify);
        if (peer>=0) close(peer);
        std::lock_guard lock(registry().mutex);
        registry().devices.erase(key);
    }
    bool selected(int type,uint32_t dev) {
        std::lock_guard lock(mutex);
        return type<int(actions.size()) && actions[type]==1 && (!filtered || !filter.count(dev));
    }
    void loss() { lost=true; }
    bool internalJournalFile(const std::string& host) const {
        /* The shared journal's own atomic ID persistence must not feed back
         * into CoreServices' raw file-ID watcher. Match only the reserved
         * prefix-root files, preserving equal user names in other scopes. */
        for (const auto& root:roots) {
            if (root.guest!="/") continue;
            const auto state=root.host+"/.darling-fsevents-id";
            if (host==state || host==state+".pending" || host==state+".lock") return true;
        }
        return false;
    }
    void path(std::vector<uint8_t>& bytes,const Entry& entry,bool packed) {
        if (entry.guest.size()+1>UINT16_MAX) { loss();return; }
        append(bytes,String);append(bytes,uint16_t(entry.guest.size()+1));
        bytes.insert(bytes.end(),entry.guest.begin(),entry.guest.end());bytes.push_back(0);
        auto& i=entry.info;
        if (!i.dev && !i.inode) return; // absent rename destination, as in XNU
        if (packed) {
            append(bytes,Finfo);append(bytes,uint16_t(24));
            // XNU emits the packed fields starting at cur->ino (8+4+4+4+4).
            append(bytes,i.inode);append(bytes,i.dev);append(bytes,i.mode);append(bytes,i.uid);append(bytes,i.gid);
        } else {
            arg(bytes,Dev,i.dev);arg(bytes,Inode,i.inode);arg(bytes,Mode,i.mode);arg(bytes,Uid,i.uid);arg(bytes,Gid,i.gid);
        }
    }
    void emit(int type,const Entry& first,const Entry* second=nullptr) {
        if (!selected(type,first.info.dev) && !(second && selected(type,second->info.dev))) return;
        if (queue.size()>=depth) { loss();return; }
        bool packed;
        { std::lock_guard lock(mutex);packed=compact; }
        std::vector<uint8_t> bytes;append(bytes,int32_t(type));append(bytes,int32_t(0));
        path(bytes,first,packed);if (second) path(bytes,*second,packed);
        // Darling's x86_64 mach_absolute_time uses Linux's monotonic nanoseconds.
        auto stamp=std::chrono::steady_clock::now().time_since_epoch();
        arg(bytes,Int64,uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(stamp).count()));
        append(bytes,Done);queue.push_back(std::move(bytes));
    }
    int inventory(const std::string& host,const std::string& guest,bool initial) {
        if (internalJournalFile(host)) return 0;
        Entry entry{host,guest,{}};
        if (!infoFor(host,entry.info)) { int error=errno;fprintf(stderr,"fsevents inventory lstat: %s: %s\n",host.c_str(),strerror(error));return -error; }
        if (entries.size()>=MaxEntries) return -ENOSPC;
        entries[host]=entry;
        if (!S_ISDIR(entry.info.mode)) return 0;
        // The Linux proc/sys/devpts mounts exposed by the container are not
        // disk-backed vnode trees. They cannot produce these legacy events,
        // and descending into /proc would also follow changing task entries.
        struct statfs filesystem;
        if (statfs(host.c_str(),&filesystem)<0) return -errno;
        switch (filesystem.f_type) {
            case 0x9fa0: case 0x62656572: case 0x1cd1: // proc, sysfs, devpts
            case 0x27e0eb: case 0x63677270: // cgroup, cgroup2
            case 0x42494e4d: case 0x6e736673: // binfmt_misc, nsfs
            case 0x74726163: case 0x73636673: case 0x64626720: // tracing/security/debug
            case 0xde5e81e4: case 0x19800202: return 0; // efivarfs, mqueue
        }
        int wd=inotify_add_watch(notify,host.c_str(),Mask|IN_ONLYDIR|IN_DONT_FOLLOW);
        if (wd<0) { int error=errno;fprintf(stderr,"fsevents inventory watch: %s: %s\n",host.c_str(),strerror(error));return -error; }
        // Directory aliases can name the same inode; preserve one stable name.
        if (watches.count(wd)) return 0;
        watches[wd]=entry;
        std::error_code error;
        fs::directory_iterator it(host,error),end;
        if (error) {fprintf(stderr,"fsevents inventory enumerate: %s: %s\n",host.c_str(),error.message().c_str());return -error.value();}
        for (;it!=end;it.increment(error)) {
            if (error) return -error.value();
            auto leaf=it->path().filename().string();
            int result=inventory(it->path().string(),guest+(guest=="/"?"":"/")+leaf,initial);
            if (result<0) {
                if (result==-ENOENT) { if (!initial) loss();continue; }
                return result;
            }
        }
        // Events may precede a newly installed subtree watch. Tell consumers
        // to rescan instead of pretending the entire interval was observed.
        if (!initial) loss();
        return 0;
    }
    void forget(const std::string& parent) {
        for (auto it=entries.begin();it!=entries.end();) {
            if (beneath(it->first,parent)) it=entries.erase(it);else ++it;
        }
        for (auto it=watches.begin();it!=watches.end();) {
            if (beneath(it->second.host,parent)) { inotify_rm_watch(notify,it->first);it=watches.erase(it); }
            else ++it;
        }
    }
    void relocate(const Entry& from,const Entry& to) {
        std::vector<Entry> changed;
        for (auto it=entries.begin();it!=entries.end();) {
            if (beneath(it->first,from.host)) {
                auto entry=it->second;entry.host=to.host+entry.host.substr(from.host.size());
                entry.guest=to.guest+entry.guest.substr(from.guest.size());
                changed.push_back(std::move(entry));it=entries.erase(it);
            } else ++it;
        }
        for (auto& entry:changed) entries[entry.host]=entry;
        for (auto& [wd,entry]:watches) if (beneath(entry.host,from.host)) {
            entry.host=to.host+entry.host.substr(from.host.size());
            entry.guest=to.guest+entry.guest.substr(from.guest.size());
        }
    }
    void event(const inotify_event& event) {
        if (event.mask&IN_Q_OVERFLOW) { moves.clear();loss();return; }
        auto watch=watches.find(event.wd);
        if (watch==watches.end()) { if (!(event.mask&IN_IGNORED)) loss();return; }
        if (event.mask&IN_IGNORED) { watches.erase(watch);return; }
        if (event.mask&IN_UNMOUNT) { loss();return; }
        if (!event.len) return; // parent watch supplies paired directory moves/deletes
        auto host=watch->second.host+"/"+event.name;
        if (internalJournalFile(host)) return;
        auto guest=watch->second.guest+(watch->second.guest=="/"?"":"/")+event.name;
        auto found=entries.find(host);
        if (event.mask&(IN_DELETE|IN_MOVED_FROM)) {
            if (found==entries.end()) { loss();return; }
            auto old=found->second;
            if (event.mask&IN_MOVED_FROM) moves[event.cookie]={old,std::chrono::steady_clock::now()};
            else { emit(Delete,old);forget(host); }
        }
        if (event.mask&IN_MOVED_TO) {
            auto pending=moves.find(event.cookie);
            if (pending!=moves.end()) {
                Entry target{host,guest,pending->second.entry.info};
                auto old=pending->second.entry;
                // XNU's second metadata tuple identifies the overwritten
                // destination, not a second copy of the source inode.
                Entry destination{host,guest,found==entries.end()?Info{}:found->second.info};
                if (found!=entries.end()) forget(host);
                relocate(old,target);emit(Rename,old,&destination);moves.erase(pending);
            } else {
                // The source is outside this watch set. We cannot invent it.
                loss();if (inventory(host,guest,false)<0) loss();
            }
        } else if (event.mask&IN_CREATE) {
            if (inventory(host,guest,false)<0) loss();
        }
    }
    void flush() {
        while (!queue.empty()) {
            auto& bytes=queue.front();
            auto n=send(peer,bytes.data(),bytes.size(),MSG_DONTWAIT|MSG_NOSIGNAL);
            if (n<0) { if (errno!=EAGAIN && errno!=EWOULDBLOCK) throw errno;return; }
            if (n!=ssize_t(bytes.size())) throw EIO;
            queue.pop_front();
        }
        if (lost) {
            std::vector<uint8_t> bytes;append(bytes,int32_t(Dropped));append(bytes,int32_t(0));append(bytes,Done);
            auto n=send(peer,bytes.data(),bytes.size(),MSG_DONTWAIT|MSG_NOSIGNAL);
            if (n==ssize_t(bytes.size())) lost=false;
            else if (n<0 && errno!=EAGAIN && errno!=EWOULDBLOCK) throw errno;
        }
    }
    void run() noexcept {
        try {
            while (true) {
                pollfd fds[2]={{peer,short(POLLIN|POLLRDHUP|((lost||!queue.empty())?POLLOUT:0)),0},{notify,POLLIN,0}};
                int n=poll(fds,notify<0?1:2,50);
                if (n<0) { if (errno==EINTR) continue;break; }
                if (fds[0].revents&(POLLHUP|POLLRDHUP|POLLERR|POLLNVAL|POLLIN)) break;
                if (notify>=0 && (fds[1].revents&POLLIN)) {
                    alignas(inotify_event) char buffer[65536];
                    auto count=read(notify,buffer,sizeof buffer);
                    if (count<0) { if (errno!=EAGAIN && errno!=EINTR) break; }
                    else for (size_t at=0;at<size_t(count);) {
                        auto* ev=reinterpret_cast<const inotify_event*>(buffer+at);
                        event(*ev);at+=sizeof(*ev)+ev->len;
                    }
                }
                auto now=std::chrono::steady_clock::now();
                for (auto it=moves.begin();it!=moves.end();) {
                    if (now-it->second.time>std::chrono::milliseconds(100)) {
                        auto host=it->second.entry.host;loss();it=moves.erase(it);forget(host);
                    } else ++it;
                }
                flush();
            }
        } catch (...) { /* A broken event channel terminates, never returns false success. */ }
    }
};
std::shared_ptr<Device> find(int fd) {
    struct stat st;
    if (fstat(fd,&st)<0) return nullptr;
    std::lock_guard lock(registry().mutex);
    auto it=registry().devices.find(st.st_ino);
    return it==registry().devices.end()?nullptr:it->second.lock();
}
int publish(const std::shared_ptr<Device>& device,int flags) {
    int pair[2];
    if (socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,pair)<0) return -errno;
    device->peer=pair[0];
    sockaddr_un name{};name.sun_family=AF_UNIX;
    auto text=std::string("darling.fsevents.v1.")+std::to_string(getpid())+"."+std::to_string(registry().serial++);
    memcpy(name.sun_path+1,text.data(),text.size());
    if (bind(pair[0],reinterpret_cast<sockaddr*>(&name),offsetof(sockaddr_un,sun_path)+1+text.size())<0) {
        int error=errno;close(pair[1]);return -error;
    }
    struct stat st;
    if (fstat(pair[1],&st)<0) { int error=errno;close(pair[1]);return -error; }
    device->key=st.st_ino;
    if (flags&O_NONBLOCK) fcntl(pair[1],F_SETFL,O_NONBLOCK);
    { std::lock_guard lock(registry().mutex);registry().devices[device->key]=device; }
    try { std::thread([device] { device->run(); }).detach(); }
    catch (...) { close(pair[1]);return -EAGAIN; }
    return pair[1];
}
}
int openDevice(const std::vector<Root>& roots,int flags) {
    if (roots.empty() || (flags&O_ACCMODE)!=O_RDONLY) return -EINVAL;
    auto device=std::make_shared<Device>();device->roots=roots;
    return publish(device,flags);
}
int cloneDevice(int fd,const std::vector<int8_t>& actions,unsigned depth) {
    auto control=find(fd);
    if (!control) return -ENOTTY;
    if (control->notify>=0) return -ENOTTY;
    if (actions.empty() || actions.size()>64 || depth==0 || depth>65536) return -EINVAL;
    for (unsigned i=0;i<actions.size();i++) {
        if (actions[i]<0 || actions[i]>1) return -EINVAL;
        if (actions[i] && i!=Delete && i!=Rename) return -ENOTSUP;
    }
    auto device=std::make_shared<Device>();device->roots=control->roots;device->actions=actions;device->depth=depth;
    device->notify=inotify_init1(IN_NONBLOCK|IN_CLOEXEC);
    if (device->notify<0) return -errno;
    for (auto& root:device->roots) {
        if (root.host.empty() || root.guest.empty() || root.guest[0]!='/') return -EINVAL;
        int result=device->inventory(root.host,root.guest,true);
        if (result<0) return result;
    }
    return publish(device,0);
}
int filterDevices(int fd,const std::vector<uint32_t>& devices) {
    auto stream=find(fd);if (!stream || stream->notify<0) return -ENOTTY;
    if (devices.size()>256) return -EINVAL;
    std::lock_guard lock(stream->mutex);stream->filter={devices.begin(),devices.end()};stream->filtered=!devices.empty();return 0;
}
int setCompact(int fd) {
    auto stream=find(fd);if (!stream || stream->notify<0) return -ENOTTY;
    std::lock_guard lock(stream->mutex);stream->compact=true;return 0;
}
int setExtended(int fd) {
    auto stream=find(fd);if (!stream || stream->notify<0) return -ENOTTY;
    std::lock_guard lock(stream->mutex);stream->extended=true;return 0;
}
bool isDevice(int fd) { return bool(find(fd)); }
size_t activeDevices() { std::lock_guard lock(registry().mutex);return registry().devices.size(); }
namespace {
Journal& sharedJournal(const std::string& prefix) {
    // Survives detached descriptor-lifetime workers until process teardown.
    static auto* mutex=new std::mutex;
    static auto* instances=new std::unordered_map<std::string,std::unique_ptr<Journal>>;
    std::lock_guard lock(*mutex);
    auto& value=(*instances)[prefix];
    if(!value)value=std::make_unique<Journal>(prefix+"/.darling-fsevents-id",std::vector<Root>{{prefix,"/"}});
    return *value;
}
}
int journalCurrent(int fd,const std::string& prefix,uint64_t& value) {
    if(!find(fd))return -ENOTTY;
    return sharedJournal(prefix).current(value);
}
int journalAddRoot(int fd,const std::string& host,const std::string& guest) {
    auto device=find(fd);if(!device)return -ENOTTY;
    std::lock_guard lock(device->mutex);
    if(device->notify>=0||device->journal)return -EBUSY;
    if(device->journalRoots.size()>=256)return -E2BIG;
    device->journalRoots.push_back({host,guest});return 0;
}
int journalBegin(int fd,const std::string& prefix,uint64_t since,uint32_t flags) {
    auto device=find(fd);if(!device)return -ENOTTY;
    std::lock_guard lock(device->mutex);
    if(device->notify>=0||device->journal)return -EBUSY;
    std::weak_ptr<Device> weak=device;
    auto& journal=sharedJournal(prefix);
    uint64_t handle=0;
    int result=journal.subscribe(device->journalRoots,since,flags,[weak](const JournalEvent& event){
        auto owner=weak.lock();if(!owner)return -1;
        struct Header {uint32_t magic,length;uint64_t id;uint32_t flags,reserved;};
        static_assert(sizeof(Header)==24);
        if(event.path.size()>16383)return -1;
        Header header{0x314a5346,uint32_t(event.path.empty()?0:event.path.size()+1),event.id,event.flags,0};
        std::vector<uint8_t> packet(sizeof header+header.length);
        memcpy(packet.data(),&header,sizeof header);
        if(header.length)memcpy(packet.data()+sizeof header,event.path.c_str(),header.length);
        auto n=send(owner->peer,packet.data(),packet.size(),MSG_DONTWAIT|MSG_NOSIGNAL);
        if(n==ssize_t(packet.size()))return 1;
        return n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)?0:-1;
    },handle,[weak]{return !weak.expired();});
    if(result<0)return result;
    device->journal=&journal;device->subscription=handle;return 0;
}
int journalBarrier(int fd,uint64_t& ticket) {
    auto device=find(fd);if(!device)return -ENOTTY;
    Journal* journal;uint64_t handle;
    {std::lock_guard lock(device->mutex);journal=device->journal;handle=device->subscription;}
    return journal?journal->barrier(handle,ticket):-ENOTTY;
}
}
