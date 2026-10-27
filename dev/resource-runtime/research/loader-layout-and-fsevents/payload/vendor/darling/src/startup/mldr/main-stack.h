/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Comman Kang
 */
#ifndef DARLING_MLDR_MAIN_STACK_H
#define DARLING_MLDR_MAIN_STACK_H
#include <errno.h>
#include <stdint.h>
#include <stddef.h>
#include <sys/mman.h>

typedef void* (*mldr_stack_mmap_fn)(void*, size_t, int, int, int, off_t);

/* Linux's initial ELF stack may occupy Darwin's preferred stack address.
 * Never replace that live mapping. A fallback reserves the requested stack
 * capacity lazily, so nearby mmap allocations cannot limit it to 64 KiB.
 * Both the preferred and fallback stack must remain below the commpage. */
static void* mldr_allocate_main_stack(uintptr_t* top, size_t initial_size,
                                    size_t capacity, mldr_stack_mmap_fn map)
{
    if (!initial_size || capacity < initial_size || capacity > *top) {
        errno = EINVAL;
        return MAP_FAILED;
    }
    const int flags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_GROWSDOWN;
    void* result = map((void*)(*top - initial_size), initial_size,
                      PROT_READ | PROT_WRITE, flags | MAP_FIXED_NOREPLACE, -1, 0);
    size_t mapped_size = initial_size;
    if (result == MAP_FAILED && errno == EEXIST) {
        mapped_size = capacity;
        result = map((void*)(*top - capacity), capacity,
                     PROT_READ | PROT_WRITE, flags, -1, 0);
    }
    if (result != MAP_FAILED) {
        if ((uintptr_t)result > *top - mapped_size) {
            munmap(result, mapped_size);
            errno = EEXIST;
            return MAP_FAILED;
        }
        *top = (uintptr_t)result + mapped_size;
    }
    return result;
}
#endif
