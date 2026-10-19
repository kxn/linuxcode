#include <darlingserver/proc-maps.hpp>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

using DarlingServer::ProcMaps::Entry;
using DarlingServer::ProcMaps::parse;

static unsigned verified_lines;
static Entry containing(const void* address) {
    std::ifstream input("/proc/self/maps");
    assert(input);
    std::string line;
    Entry found;
    bool present = false;
    while (std::getline(input, line)) {
        Entry entry;
        assert(parse(line, entry));
        unsigned long long start, end, offset, inode;
        unsigned major, minor;
        char permission[5];
        assert(sscanf(line.c_str(), "%llx-%llx %4s %llx %x:%x %llu",
            &start, &end, permission, &offset, &major, &minor, &inode) == 7);
        assert(entry.start == start && entry.end == end && entry.offset == offset);
        assert(entry.device == makedev(major, minor) && entry.inode == inode);
        int protection = (permission[0] == 'r' ? PROT_READ : 0)
            | (permission[1] == 'w' ? PROT_WRITE : 0) | (permission[2] == 'x' ? PROT_EXEC : 0);
        assert(entry.protection == protection && entry.shared == (permission[3] == 's'));
        ++verified_lines;
        if (entry.start <= (uintptr_t)address && (uintptr_t)address < entry.end) {
            found = entry;
            present = true;
        }
    }
    assert(present);
    return found;
}

int main() {
    const char* malformed[] = {
        "", "bad", "1000-1000 rw-p 0 00:00 0", "2000-1000 rw-p 0 00:00 0",
        "1000-2000 rw-q 0 00:00 0", "1000-2000 rrrp 0 00:00 0",
        "-1-2000 rw-p 0 00:00 0", "10000000000000000-2000 rw-p 0 00:00 0",
        "1000-2000 rw-p 10000000000000000 00:00 0", "1000-2000 rw-p 0 100000000:00 0",
        "1000-2000 rw-p 0 00:100000000 0", "1000-2000 rw-p 0 00:00 18446744073709551616",
        "1000-2000 rw-p 0 00:00 -1", "1000-2000 rw-p 0 00:00 1garbage",
        "1000-2000 rw-p 0 00:00", "garbage 1000-2000 rw-p 0 00:00 0"
    };
    for (auto line : malformed) {
        Entry entry; entry.start = 0x123; entry.inode = 0x456;
        assert(!parse(line, entry) && entry.start == 0x123 && entry.inode == 0x456);
    }
    Entry entry;
    assert(parse("1000-3000 r-xs 00002000 103:ab 12345 /file name: with spaces (deleted)", entry));
    assert(entry.start == 4096 && entry.end == 12288 && entry.offset == 8192);
    assert(entry.device == makedev(0x103, 0xab) && entry.inode == 12345);
    assert(entry.protection == (PROT_READ | PROT_EXEC) && entry.shared);

    size_t page = sysconf(_SC_PAGESIZE);
    int fd = memfd_create("proc-maps file with spaces", MFD_CLOEXEC); assert(fd >= 0);
    assert(ftruncate(fd, page * 3) == 0);
    void* mapping = mmap(nullptr, page, PROT_READ, MAP_SHARED, fd, page);
    assert(mapping != MAP_FAILED);
    struct stat identity;
    assert(fstat(fd, &identity) == 0);
    entry = containing(mapping);
    assert(entry.device == (uint64_t)identity.st_dev && entry.inode == (uint64_t)identity.st_ino);
    assert(entry.offset + (uintptr_t)mapping - entry.start == page);
    assert(entry.protection == PROT_READ && entry.shared);
    assert(mprotect(mapping, page, PROT_READ | PROT_WRITE) == 0);
    entry = containing(mapping);
    assert(entry.protection == (PROT_READ | PROT_WRITE));
    assert(munmap(mapping, page) == 0); close(fd);

    void* private_mapping = mmap(nullptr, page * 4, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(private_mapping != MAP_FAILED);
    assert(mprotect((char*)private_mapping + page, page, PROT_READ) == 0);
    assert(containing(private_mapping).protection == (PROT_READ | PROT_WRITE));
    entry = containing((char*)private_mapping + page);
    assert(entry.protection == PROT_READ && !entry.shared);
    assert(containing((char*)private_mapping + page * 2).protection == (PROT_READ | PROT_WRITE));
    assert(munmap(private_mapping, page * 4) == 0);
    printf("PROC_MAPS_REAL_REFERENCE_AND_FSTAT_OFFSET_PROTECTION_OK lines=%u malformed=%zu\n",
        verified_lines, sizeof(malformed) / sizeof(*malformed));
}
