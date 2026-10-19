/* Linux /proc/maps numeric fields; shared with the native parser regression. */
#ifndef DARLINGSERVER_PROC_MAPS_HPP
#define DARLINGSERVER_PROC_MAPS_HPP
#include <charconv>
#include <cstdint>
#include <string_view>
#include <sys/mman.h>
#include <sys/sysmacros.h>

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
}
#endif
