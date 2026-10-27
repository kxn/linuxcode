#include <darlingserver/fsevents-device.hpp>
#include <sys/socket.h>
#include <sys/stat.h>
#include <poll.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <chrono>
#include <thread>
namespace F=DarlingServer::FSEvents;
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL line=%d %s errno=%d\n",__LINE__,#x,errno); exit(1); } } while(0)
template<class T> T load(const std::vector<uint8_t>& bytes,size_t at) {
    CHECK(at+sizeof(T)<=bytes.size());T value;memcpy(&value,bytes.data()+at,sizeof value);return value;
}
struct Event { int type,pid;std::vector<std::string> paths;std::vector<uint64_t> inodes;std::vector<uint32_t> devices;bool compact=false; };
static Event readEvent(int fd) {
    pollfd p={fd,POLLIN,0};CHECK(poll(&p,1,4000)==1);CHECK(p.revents&POLLIN);
    std::vector<uint8_t> bytes(32768);auto n=read(fd,bytes.data(),bytes.size());CHECK(n>=10);bytes.resize(n);
    Event out{load<int32_t>(bytes,0),load<int32_t>(bytes,4),{},{},{},false};
    bool done=false;size_t at=8;
    while(at<bytes.size()) {
        auto type=load<uint16_t>(bytes,at);at+=2;
        if(type==0xb33f) {done=true;break;}
        auto count=load<uint16_t>(bytes,at);at+=2;CHECK(at+count<=bytes.size());
        if(type==2) {CHECK(count>0 && bytes[at+count-1]==0);out.paths.emplace_back(reinterpret_cast<char*>(bytes.data()+at),count-1);}
        if(type==7) {CHECK(count==8);out.inodes.push_back(load<uint64_t>(bytes,at));}
        if(type==9) {CHECK(count==4);out.devices.push_back(load<uint32_t>(bytes,at));}
        if(type==12) {CHECK(count==24);out.compact=true;out.inodes.push_back(load<uint64_t>(bytes,at));out.devices.push_back(load<uint32_t>(bytes,at+8));}
        if(type==5) {CHECK(count==8);CHECK(load<uint64_t>(bytes,at)>0);}
        at+=count;
    }
    CHECK(done && at==bytes.size());CHECK(out.pid==0);return out;
}
static void noEvent(int fd) {pollfd p={fd,POLLIN,0};CHECK(poll(&p,1,150)==0);}
static void writeFile(const std::string& path) {std::ofstream out(path);out<<"original bytes";CHECK(out.good());}
static struct stat info(const std::string& path) {struct stat st;CHECK(lstat(path.c_str(),&st)==0);return st;}
int main() {
    char temporary[]="/tmp/linuxcode-fsevents-XXXXXX";auto* temp=mkdtemp(temporary);CHECK(temp);
    std::string root=temp;std::filesystem::create_directory(root+"/nested");
    for(auto name:{"remove","from","replace-from","replace-to","filtered","compact","nested/child","outside"}) writeFile(root+"/"+name);
    auto removed=info(root+"/remove"),moved=info(root+"/from"),replacement=info(root+"/replace-to"),compact=info(root+"/compact");
    std::vector<int8_t> actions(16);actions[1]=actions[3]=1;
    CHECK(F::openDevice({},O_RDONLY)==-EINVAL);
    CHECK(F::openDevice({{root,"/guest"}},O_WRONLY)==-EINVAL);
    int device=F::openDevice({{root,"/guest"}},O_RDONLY);CHECK(device>=0);CHECK(F::isDevice(device));
    CHECK(F::cloneDevice(-1,actions,32)==-ENOTTY);
    CHECK(F::cloneDevice(device,actions,0)==-EINVAL);
    CHECK(F::cloneDevice(device,actions,65537)==-EINVAL);
    auto unsupported=actions;unsupported[0]=1;CHECK(F::cloneDevice(device,unsupported,32)==-ENOTSUP);
    unsupported[0]=2;CHECK(F::cloneDevice(device,unsupported,32)==-EINVAL);
    int stream=F::cloneDevice(device,actions,32);CHECK(stream>=0);CHECK(F::isDevice(stream));
    CHECK(F::cloneDevice(stream,actions,32)==-ENOTTY);CHECK(F::filterDevices(device,{})==-ENOTTY);
    CHECK(F::filterDevices(stream,std::vector<uint32_t>(257))==-EINVAL);
    CHECK(unlink((root+"/remove").c_str())==0);
    auto e=readEvent(stream);CHECK(e.type==1);CHECK(e.paths==std::vector<std::string>{"/guest/remove"});
    CHECK(e.inodes==std::vector<uint64_t>{removed.st_ino});CHECK(e.devices==std::vector<uint32_t>{uint32_t(removed.st_dev)});
    CHECK(rename((root+"/from").c_str(),(root+"/to").c_str())==0);
    e=readEvent(stream);CHECK(e.type==3);CHECK((e.paths==std::vector<std::string>{"/guest/from","/guest/to"}));
    CHECK(e.inodes==std::vector<uint64_t>{moved.st_ino}); // absent destination has no metadata tuple
    CHECK(rename((root+"/replace-from").c_str(),(root+"/replace-to").c_str())==0);
    e=readEvent(stream);CHECK(e.type==3);CHECK(e.inodes.size()==2);CHECK(e.inodes[1]==replacement.st_ino);
    CHECK(rename((root+"/nested").c_str(),(root+"/renamed").c_str())==0);
    e=readEvent(stream);CHECK(e.type==3);CHECK(e.paths[1]=="/guest/renamed");
    CHECK(unlink((root+"/renamed/child").c_str())==0);
    e=readEvent(stream);CHECK(e.type==1);CHECK(e.paths[0]=="/guest/renamed/child");
    CHECK(F::filterDevices(stream,{uint32_t(removed.st_dev)})==0);
    CHECK(unlink((root+"/filtered").c_str())==0);noEvent(stream);
    CHECK(F::filterDevices(stream,{})==0);CHECK(F::setCompact(stream)==0);CHECK(F::setExtended(stream)==0);
    CHECK(unlink((root+"/compact").c_str())==0);
    e=readEvent(stream);CHECK(e.type==1 && e.compact);CHECK(e.inodes==std::vector<uint64_t>{compact.st_ino});
    int duplicate=dup(stream);CHECK(duplicate>=0 && F::isDevice(duplicate));CHECK(close(stream)==0);
    CHECK(unlink((root+"/to").c_str())==0);e=readEvent(duplicate);CHECK(e.type==1 && e.paths[0]=="/guest/to");
    std::string outside=root+"-outside";CHECK(rename((root+"/outside").c_str(),outside.c_str())==0);
    e=readEvent(duplicate);CHECK(e.type==999 && e.paths.empty());CHECK(unlink(outside.c_str())==0);
    CHECK(close(duplicate)==0);CHECK(close(device)==0);
    auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(3);
    while(F::activeDevices() && std::chrono::steady_clock::now()<deadline) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    CHECK(F::activeDevices()==0);std::filesystem::remove_all(root);
    printf("FSEVENTS_DEVICE_REAL_LINUX_OK checks=%u pid_provenance=unavailable event_selection=delete,rename\n",checks);
}
