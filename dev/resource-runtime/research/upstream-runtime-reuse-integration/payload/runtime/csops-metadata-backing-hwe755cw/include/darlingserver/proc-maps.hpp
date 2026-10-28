/* Linux /proc/maps numeric fields; shared with the native parser regression. */
#ifndef DARLINGSERVER_PROC_MAPS_HPP
#define DARLINGSERVER_PROC_MAPS_HPP
#include <charconv>
#include <cstdint>
#include <string_view>
#include <sys/mman.h>
#include <sys/sysmacros.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fstream>
#include <string>

namespace DarlingServer::ProcMaps {
struct Entry {
    uint64_t start = 0, end = 0, offset = 0, device = 0, inode = 0;
    int protection = 0;
    bool shared = false;
};

inline bool parse(std::string_view line, Entry& output) {
    if (line.empty()) return false;
    const char* cursor = line.data();
    const char* end = cursor + line.size();
    auto integer = [&](auto& value, int base) {
        auto result = std::from_chars(cursor, end, value, base);
        if (result.ec != std::errc() || result.ptr == cursor) return false;
        cursor = result.ptr;
        return true;
    };
    auto separator = [&](char value) {
        if (cursor == end || *cursor != value) return false;
        ++cursor;
        return true;
    };
    auto spaces = [&]() {
        const char* first = cursor;
        while (cursor != end && (*cursor == ' ' || *cursor == '\t')) ++cursor;
        return cursor != first;
    };
    Entry entry;
    unsigned major = 0, minor = 0;
    if (!integer(entry.start, 16) || !separator('-') || !integer(entry.end, 16)
        || entry.start >= entry.end || !spaces() || end - cursor < 4) return false;
    const char* permission = cursor;
    if ((permission[0] != 'r' && permission[0] != '-')
        || (permission[1] != 'w' && permission[1] != '-')
        || (permission[2] != 'x' && permission[2] != '-')
        || (permission[3] != 'p' && permission[3] != 's')) return false;
    cursor += 4;
    if (!spaces() || !integer(entry.offset, 16) || !spaces()
        || !integer(major, 16) || !separator(':') || !integer(minor, 16)
        || !spaces() || !integer(entry.inode, 10)
        || (cursor != end && *cursor != ' ' && *cursor != '\t')) return false;
    if (permission[0] == 'r') entry.protection |= PROT_READ;
    if (permission[1] == 'w') entry.protection |= PROT_WRITE;
    if (permission[2] == 'x') entry.protection |= PROT_EXEC;
    entry.shared = permission[3] == 's';
    entry.device = makedev(major, minor);
    output = entry;
    return true;
}
// Linux overlayfs may present one st_dev through fstat while the VMA uses its
// real backing file's device. Obtain that relationship from the kernel itself:
// mmap this very descriptor, retain the VMA, and compare its /proc identity to
// the target VMA. Never infer equality from an inode or pathname alone.
struct FileMappingProof {
    Entry descriptorMapping{}, targetMapping{};
    struct stat before{}, after{};
    const char* stage = "initial";
};
inline bool sameFileSnapshot(const struct stat& a,const struct stat& b) {
    return a.st_dev==b.st_dev && a.st_ino==b.st_ino && a.st_size==b.st_size &&
        a.st_mtim.tv_sec==b.st_mtim.tv_sec && a.st_mtim.tv_nsec==b.st_mtim.tv_nsec &&
        a.st_ctim.tv_sec==b.st_ctim.tv_sec && a.st_ctim.tv_nsec==b.st_ctim.tv_nsec;
}
inline bool mappingAt(pid_t pid,uint64_t address,Entry& output) {
    std::ifstream maps("/proc/"+std::to_string(pid)+"/maps");std::string line;
    while(std::getline(maps,line)) {
        Entry entry;
        if(parse(line,entry) && entry.start<=address && address<entry.end) {output=entry;return true;}
    }
    return false;
}
inline bool mappedFileMatches(int fd,pid_t pid,uint64_t address,uint64_t fileOffset,
    const struct stat& verifiedFile,FileMappingProof& proof) {
    proof={};proof.stage="descriptor-stat-before";
    if(fstat(fd,&proof.before) || !S_ISREG(proof.before.st_mode) || !sameFileSnapshot(verifiedFile,proof.before))return false;
    long pageSize=sysconf(_SC_PAGESIZE);proof.stage="page-size";if(pageSize<=0)return false;
    proof.stage="descriptor-mmap";
    void* mapping=mmap(nullptr,static_cast<size_t>(pageSize),PROT_READ,MAP_PRIVATE,fd,0);
    if(mapping==MAP_FAILED)return false;
    struct Mapping {void* address;size_t size;~Mapping(){munmap(address,size);}} hold{mapping,static_cast<size_t>(pageSize)};
    uint64_t local=reinterpret_cast<uintptr_t>(mapping);
    proof.stage="descriptor-vma";
    if(!mappingAt(getpid(),local,proof.descriptorMapping) || !proof.descriptorMapping.inode ||
        proof.descriptorMapping.offset>UINT64_MAX-(local-proof.descriptorMapping.start) ||
        proof.descriptorMapping.offset+local-proof.descriptorMapping.start!=0)return false;
    proof.stage="target-vma";
    if(!mappingAt(pid,address,proof.targetMapping) || !proof.targetMapping.inode)return false;
    const Entry& own=proof.descriptorMapping;const Entry& target=proof.targetMapping;
    proof.stage="backing-device-inode-offset";
    if(own.device!=target.device || own.inode!=target.inode ||
        target.offset>UINT64_MAX-(address-target.start) ||
        target.offset+address-target.start!=fileOffset)return false;
    proof.stage="descriptor-stat-after";
    if(fstat(fd,&proof.after) || !sameFileSnapshot(proof.before,proof.after))return false;
    proof.stage="matched";return true;
}

}
#endif
