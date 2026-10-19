#include <assert.h>
#include <dirent.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach/memory_object_types.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "memory-entry-test-utils.h"

static const size_t page = 4096;
static unsigned aliases_checked;

static mach_vm_address_t allocate(size_t length) {
    mach_vm_address_t address = 0;
    assert(mach_vm_allocate(mach_task_self(), &address, length, VM_FLAGS_ANYWHERE) == KERN_SUCCESS);
    return address;
}

static mach_vm_address_t alias(mach_vm_address_t source, size_t length, int flags, vm_prot_t* protection) {
    mach_vm_address_t address = 0;
    vm_prot_t maximum = VM_PROT_NONE, current = VM_PROT_NONE;
    kern_return_t status = mach_vm_remap(mach_task_self(), &address, length, 0, flags,
        mach_task_self(), source, FALSE, &current, &maximum, VM_INHERIT_NONE);
    if (status) fprintf(stderr, "REMAP_FAILED status=%d size=%zu flags=%x\n", status, length, flags);
    assert(status == KERN_SUCCESS && address);
    assert(maximum == VM_PROT_ALL);
    if (protection) *protection = current;
    ++aliases_checked;
    return address;
}

static void release(mach_vm_address_t address, size_t length) {
    assert(mach_vm_deallocate(mach_task_self(), address, length) == KERN_SUCCESS);
}

static void pattern(mach_vm_address_t address, size_t length, unsigned seed) {
    for (size_t i = 0; i < length; ++i)
        ((unsigned char*)address)[i] = (unsigned char)(seed + i * 37 + (i / page) * 11);
}

static vm_prot_t protection_at(mach_vm_address_t address) {
    mach_vm_address_t start = address;
    mach_vm_size_t size = 0;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object = MACH_PORT_NULL;
    assert(mach_vm_region(mach_task_self(), &start, &size, VM_REGION_BASIC_INFO_64,
        (vm_region_info_t)&info, &count, &object) == KERN_SUCCESS);
    assert(start <= address && address < start + size);
    if (object) assert(mach_port_deallocate(mach_task_self(), object) == KERN_SUCCESS);
    return info.protection;
}

static unsigned remap_backings(unsigned long pid) {
    char directory[256];
    snprintf(directory, sizeof(directory), "/Volumes/SystemRoot/proc/%lu/fd", pid);
    DIR* stream = opendir(directory); assert(stream);
    struct dirent* item;
    unsigned count = 0;
    while ((item = readdir(stream))) {
        char name[512], target[512];
        snprintf(name, sizeof(name), "%s/%s", directory, item->d_name);
        ssize_t size = readlink(name, target, sizeof(target) - 1);
        if (size < 0) continue;
        target[size] = 0;
        if (strstr(target, "memfd:darling-remapped")) ++count;
    }
    closedir(stream);
    return count;
}

static void expect_failure(mach_vm_address_t source, size_t length, mach_vm_offset_t mask, int flags) {
    mach_vm_address_t address = 0x12345000;
    vm_prot_t current = 0x123, maximum = 0x456;
    assert(mach_vm_remap(mach_task_self(), &address, length, mask, flags,
        mach_task_self(), source, FALSE, &current, &maximum, VM_INHERIT_NONE) != KERN_SUCCESS);
    assert(address == 0x12345000 && current == 0x123 && maximum == 0x456);
}

int main(void) {
    assert(getpagesize() == page);
    unsigned long server = server_pid();
    unsigned baseline = remap_backings(server);
    mach_vm_address_t source = allocate(3 * page);
    pattern(source, 3 * page, 19);
    unsigned char expected[3 * 4096];
    memcpy(expected, (void*)source, sizeof(expected));
    mach_vm_address_t one = alias(source, page, VM_FLAGS_ANYWHERE, NULL);
    assert(!memcmp((void*)one, expected, page));
    puts("SHARED_REMAP_INCREMENTAL_GROW_BEGIN"); fflush(stdout);
    mach_vm_address_t two = alias(source, 2 * page, VM_FLAGS_ANYWHERE | VM_FLAGS_RANDOM_ADDR, NULL);
    mach_vm_address_t three = alias(source, 3 * page, VM_FLAGS_ANYWHERE, NULL);
    assert(!memcmp((void*)two, expected, 2 * page));
    assert(!memcmp((void*)three, expected, 3 * page));
    ((unsigned char*)one)[17] ^= 0x71;
    expected[17] ^= 0x71;
    ((unsigned char*)two)[page + 23] ^= 0x32;
    expected[page + 23] ^= 0x32;
    ((unsigned char*)three)[2 * page + 29] ^= 0x53;
    expected[2 * page + 29] ^= 0x53;
    assert(!memcmp((void*)source, expected, 3 * page));
    assert(!memcmp((void*)one, expected, page));
    assert(!memcmp((void*)two, expected, 2 * page));
    assert(!memcmp((void*)three, expected, 3 * page));
    mach_vm_address_t stitched = alias(three + page, 2 * page, VM_FLAGS_ANYWHERE, NULL);
    assert(!memcmp((void*)stitched, expected + page, 2 * page));

    release(source, 3 * page);
    mach_vm_address_t reused = source;
    assert(mach_vm_allocate(mach_task_self(), &reused, 3 * page, VM_FLAGS_FIXED) == KERN_SUCCESS && reused == source);
    pattern(reused, 3 * page, 81);
    mach_vm_address_t fresh = alias(reused, 3 * page, VM_FLAGS_ANYWHERE, NULL);
    assert(!memcmp((void*)fresh, (void*)reused, 3 * page));
    ((unsigned char*)fresh)[17] ^= 0x22;
    assert(((unsigned char*)fresh)[17] == ((unsigned char*)reused)[17]);
    assert(!memcmp((void*)three, expected, 3 * page));
    release(reused, 3 * page); release(fresh, 3 * page);
    release(one, page); release(two, 2 * page); release(three, 3 * page);
    assert(!memcmp((void*)stitched, expected + page, 2 * page));
    release(stitched, 2 * page);

    mach_vm_address_t wide = allocate(4 * page);
    pattern(wide, 4 * page, 37);
    mach_vm_address_t whole = alias(wide, 4 * page, VM_FLAGS_ANYWHERE, NULL);
    mach_vm_address_t sub = alias(whole + page, 2 * page, VM_FLAGS_ANYWHERE, NULL);
    mach_vm_address_t nested = alias(sub + page, page, VM_FLAGS_ANYWHERE, NULL);
    assert(!memcmp((void*)sub, (void*)(wide + page), 2 * page));
    assert(!memcmp((void*)nested, (void*)(wide + 2 * page), page));
    ((unsigned char*)nested)[31] ^= 0x56;
    assert(((unsigned char*)nested)[31] == ((unsigned char*)wide)[2 * page + 31]);
    assert(((unsigned char*)sub)[page + 31] == ((unsigned char*)nested)[31]);
    mach_vm_address_t legacy = alias(wide + 2 * page - 16, 32, VM_FLAGS_ANYWHERE, NULL);
    assert(!(legacy & (page - 1)));
    assert(!memcmp((void*)legacy, (void*)(wide + page), page));
    mach_vm_address_t unaligned = alias(wide + 2 * page - 16, 32,
        VM_FLAGS_ANYWHERE | VM_FLAGS_RETURN_DATA_ADDR, NULL);
    assert((unaligned & (page - 1)) == page - 16);
    assert(!memcmp((void*)unaligned, (void*)(wide + 2 * page - 16), 32));
    release(legacy, page); release(unaligned & ~(page - 1), 2 * page);

    assert(mach_vm_protect(mach_task_self(), wide + 2 * page, page, FALSE, VM_PROT_READ) == KERN_SUCCESS);
    vm_prot_t common;
    mach_vm_address_t mixed = alias(wide + page, 2 * page, VM_FLAGS_ANYWHERE, &common);
    assert(common == VM_PROT_READ);
    assert(protection_at(mixed) == (VM_PROT_READ | VM_PROT_WRITE));
    assert(protection_at(mixed + page) == VM_PROT_READ);
    assert(!memcmp((void*)mixed, (void*)(wide + page), 2 * page));
    release(mixed, 2 * page);
    unsigned char saved[4096]; memcpy(saved, (void*)nested, page);
    release(wide, 4 * page); release(whole, 4 * page); release(sub, 2 * page);
    assert(!memcmp((void*)nested, saved, page));
    release(nested, page);

    mach_vm_address_t hole = allocate(3 * page);
    pattern(hole, 3 * page, 13);
    release(hole + page, page);
    expect_failure(hole, 3 * page, 0, VM_FLAGS_ANYWHERE);
    assert(((unsigned char*)hole)[37] == (unsigned char)(13 + 37 * 37));
    expect_failure(hole, 0, 0, VM_FLAGS_ANYWHERE);
    expect_failure(UINT64_MAX - 12, 8192, 0, VM_FLAGS_ANYWHERE);
    expect_failure(hole, page, 4095, VM_FLAGS_ANYWHERE);
    expect_failure(hole, page, 0, VM_FLAGS_FIXED);
    release(hole, page); release(hole + 2 * page, page);
    void* untracked = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    assert(untracked != MAP_FAILED);
    ((unsigned char*)untracked)[41] = 0x73;
    expect_failure((mach_vm_address_t)untracked, page, 0, VM_FLAGS_ANYWHERE);
    assert(((unsigned char*)untracked)[41] == 0x73);
    assert(munmap(untracked, page) == 0);

    memory_object_size_t unused_size = page;
    mach_port_t unused = MACH_PORT_NULL;
    assert(mach_make_memory_entry_64(mach_task_self(), &unused_size, 0,
        VM_PROT_READ | VM_PROT_IS_MASK, &unused, MACH_PORT_NULL) == KERN_INVALID_ADDRESS);
    assert(remap_backings(server) == baseline);
    printf("SHARED_REMAP_GROW_STITCH_NESTED_OFFSETS_ALIAS_LIFETIME_ADDRESS_REUSE_PROTECTIONS_ROUNDING_ERRORS_FD_CLEANUP_OK aliases=%u\n", aliases_checked);
    return 0;
}
