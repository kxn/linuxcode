/* Preserve the native token construction/verification; load it after libSystem
 * initialization so its dependency graph cannot reorder libSystem startup. */
#include <dlfcn.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

static uint32_t (*make_token)(pid_t, unsigned);
static bool (*verify_token)(uint32_t, unsigned);
static int (*release_file)(const char *);
static char *(*issue_mach_to_pid)(const char *, const char *, uint32_t, pid_t);
static pthread_once_t once = PTHREAD_ONCE_INIT;
static void load_backend(void) {
    const char *path = "/Volumes/SystemRoot/workspace/runtime/foundation-native-library-stage/libDarlingNativeSandbox.dylib";
    void *handle = dlopen(path, RTLD_LAZY | RTLD_LOCAL);
    if (handle) {
        make_token = dlsym(handle, "rootless_trusted_by_self_token");
        verify_token = dlsym(handle, "rootless_verify_trusted_by_self_token");
        release_file = dlsym(handle, "sandbox_extension_release_file");
        issue_mach_to_pid = dlsym(handle, "sandbox_extension_issue_mach_to_process_by_pid");
    }
    Dl_info owner;
    if (!make_token || !verify_token || !release_file || !issue_mach_to_pid || !dladdr((void *)make_token, &owner) || strcmp(owner.dli_fname, path)
        || !dladdr((void *)verify_token, &owner) || strcmp(owner.dli_fname, path)
        || !dladdr((void *)release_file, &owner) || strcmp(owner.dli_fname, path)
        || !dladdr((void *)issue_mach_to_pid, &owner) || strcmp(owner.dli_fname, path)) {
        fputs("Darling: original rootless token backend unavailable or wrong owner\n", stderr);
        abort();
    }
}
uint32_t rootless_trusted_by_self_token(pid_t pid, unsigned bit) {
    pthread_once(&once, load_backend);
    return make_token(pid, bit);
}
bool rootless_verify_trusted_by_self_token(uint32_t token, unsigned bit) {
    pthread_once(&once, load_backend);
    return verify_token(token, bit);
}
int sandbox_extension_release_file(const char *path) {
    pthread_once(&once, load_backend);
    return release_file(path);
}
/* Original Intel wrapper takes two pointers, 32-bit flags, and a pid.
 * It retains the native issuer's flags, target validation, and errors. */
char *sandbox_extension_issue_mach_to_process_by_pid(const char *extension_class,
        const char *name, uint32_t flags, pid_t pid) {
    pthread_once(&once, load_backend);
    return issue_mach_to_pid(extension_class, name, flags, pid);
}
