/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Comman Kang
 */
#ifndef DARLING_MLDR_INITIAL_STACK_H
#define DARLING_MLDR_INITIAL_STACK_H
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Re-exec only before any loader/RPC initialization, and only when Darwin's
 * fixed commpage would destroy live Linux argc/argv/envp/auxv storage. The
 * kernel chooses another randomized initial layout; ASLR is not disabled.
 * Retired stack pages remain handled by commpage_finalize after switching.
 * An unrelated mapping must never be overwritten or treated as this case. */
static int mldr_initial_stack_is_live(uintptr_t initial, uintptr_t address,
                                      size_t length)
{
    if (!length || address > UINTPTR_MAX - length) return 0;
    FILE* maps = fopen("/proc/self/maps", "r");
    if (!maps) return -1;
    char line[4096];int live = 0;
    while (fgets(line, sizeof(line), maps)) {
        unsigned long low, high;
        if (sscanf(line, "%lx-%lx", &low, &high) == 2 && strstr(line, "[stack]") &&
                initial >= low && initial < high && address < high &&
                address + length > initial) { live = 1;break; }
    }
    fclose(maps);return live;
}

static int mldr_prepare_initial_stack(char** argv, uintptr_t address, size_t length)
{
    int live = mldr_initial_stack_is_live((uintptr_t)(argv - 1), address, length);
    if (live <= 0) return live;
    const char* key = "__mldr_stack_attempt";
    const char* value = getenv(key);unsigned attempt = 0;
    if (value) {
        char* end;errno = 0;unsigned long n = strtoul(value, &end, 10);
        if (errno || !*value || *end || n >= 16) { errno = EADDRNOTAVAIL;return -1; }
        attempt = n;
    }
    char next[16];snprintf(next, sizeof(next), "%u", attempt + 1);
    if (setenv(key, next, 1) < 0) return -1;
    extern char** environ;
    execve("/proc/self/exe", argv, environ);
    return -1;
}
#endif
