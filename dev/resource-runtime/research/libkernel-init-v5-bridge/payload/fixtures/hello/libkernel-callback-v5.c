#include <dlfcn.h>
#include <errno.h>
#include <mach/mach.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d errno=%d %s\n", __LINE__, errno, #x); return 1; } } while (0)
static unsigned typed_calls;
static void *typed_malloc(size_t size, uint64_t type) { ++typed_calls; return malloc(size); }
static void typed_free(void *p, uint64_t type) { ++typed_calls; free(p); }
static void *typed_realloc(void *p, size_t size, uint64_t type) { ++typed_calls; return realloc(p, size); }
int main(int argc, char **argv) {
    setbuf(stdout, NULL);
    if (argc == 2 && !strcmp(argv[1], "--spawn-child")) { puts("LIBKERNEL_V5_REAL_SPAWN_CHILD_OK"); return 0; }
    void *h = dlopen("/usr/lib/system/libsystem_kernel.dylib", RTLD_LAZY | RTLD_LOCAL); CHECK(h);
    void (*initialize)(const void *, const char **, const char **, const void *) = dlsym(h, "__libkernel_init");
    void *(*bridge)(void) = dlsym(h, "elfcalls_get_pointer"); CHECK(initialize && bridge);
    Dl_info info; CHECK(dladdr((void *)initialize, &info));
    unsigned char *base = (unsigned char *)info.dli_fbase;
    const uintptr_t *legacy = *(const uintptr_t **)(base + KERNEL_FN_PTR_OFFSET);
    CHECK(legacy && legacy[0] == 4 && legacy[13] && legacy[14] && legacy[15] && legacy[16]);
    uintptr_t callbacks[4]; memcpy(callbacks, base + DARLING_CALLBACKS_OFFSET, sizeof(callbacks));
    CHECK(callbacks[0] == legacy[13] && callbacks[3] == legacy[16]);
    void *original_bridge = bridge(); CHECK(original_bridge);
    size_t page = (size_t)getpagesize();
    unsigned char *mapping = mmap(NULL, page * 2, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0); CHECK(mapping != MAP_FAILED);
    CHECK(mprotect(mapping, page, PROT_READ | PROT_WRITE) == 0);
    uintptr_t *v5 = (uintptr_t *)(mapping + page - 16 * sizeof(uintptr_t));
    memcpy(v5, legacy, 13 * sizeof(uintptr_t)); v5[0] = 5;
    v5[13] = (uintptr_t)typed_malloc; v5[14] = (uintptr_t)typed_free; v5[15] = (uintptr_t)typed_realloc;
    CHECK(mprotect(mapping, page, PROT_READ) == 0);
    const char *apple[] = {NULL}; mach_port_t task = mach_task_self(); CHECK(task != MACH_PORT_NULL);
    /* Exercise the exact bridge bootstrap with no private callbacks. The
     * public mach_init once guard has already run in this test process, so
     * enter the pinned bootstrap directly before replaying the public API. */
    void **bridge_store = dlsym(h, "_elfcalls"); CHECK(bridge_store && *bridge_store == original_bridge);
    char entry[80]; snprintf(entry, sizeof(entry), "elf_calls=%llx", (unsigned long long)(uintptr_t)original_bridge);
    const char *first_apple[] = {entry, NULL};
    if (getenv("LINUXCODE_PROBE_PAUSE")) { printf("BOOTSTRAP_APPLE_ENTRY %s original=%p store=%p\n", entry, original_bridge, bridge_store); sleep(20); }
    memset(base + DARLING_CALLBACKS_OFFSET, 0, sizeof(callbacks)); *bridge_store = NULL;
    void (*bootstrap)(const char **) = (void *)(base + MACH_DRIVER_INIT_OFFSET);
    bootstrap(first_apple);
    initialize(v5, (const char **)environ, first_apple, NULL);
    CHECK(typed_calls == 0 && bridge() == original_bridge && mach_task_self() == task);
    uintptr_t empty[4] = {0}; CHECK(!memcmp(empty, base + DARLING_CALLBACKS_OFFSET, sizeof(empty)));
    pid_t absent_pid; char *absent_args[] = {argv[0], "--spawn-child", NULL};
    CHECK(posix_spawn(&absent_pid, argv[0], NULL, NULL, absent_args, environ) == ENOTSUP);
    CHECK(typed_calls == 0);
    memcpy(base + DARLING_CALLBACKS_OFFSET, callbacks, sizeof(callbacks));
    initialize(v5, (const char **)environ, apple, NULL);
    CHECK(typed_calls == 0 && bridge() == original_bridge && mach_task_self() == task);
    CHECK(!memcmp(callbacks, base + DARLING_CALLBACKS_OFFSET, sizeof(callbacks)));
    CHECK(*(const void **)(base + KERNEL_FN_PTR_OFFSET) == v5);
    for (unsigned i = 0; i < 4; ++i) {
        pid_t pid; int status; char *child_args[] = {argv[0], "--spawn-child", NULL};
        CHECK(posix_spawn(&pid, argv[0], NULL, NULL, child_args, environ) == 0);
        CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    }
    CHECK(typed_calls == 0 && !memcmp(callbacks, base + DARLING_CALLBACKS_OFFSET, sizeof(callbacks)));
    initialize(legacy, (const char **)environ, apple, NULL);
    CHECK(*(const void **)(base + KERNEL_FN_PTR_OFFSET) == legacy);
    CHECK(munmap(mapping, page * 2) == 0);
    puts("LIBKERNEL_V5_GUARD_PAGE_PRIVATE_CALLBACKS_BRIDGE_AND_REAL_SPAWN_OK");
    return 0;
}
