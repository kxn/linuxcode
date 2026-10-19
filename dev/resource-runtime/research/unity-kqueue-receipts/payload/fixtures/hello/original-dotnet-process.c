#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <crt_externs.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

/* Layout from dotnet/runtime v7.0.13 System.Native/pal_io.h. */
typedef struct {
    int32_t flags, mode;
    uint32_t uid, gid;
    int64_t size, atime, atime_nsec, mtime, mtime_nsec, ctime, ctime_nsec;
    int64_t birthtime, birthtime_nsec, dev, rdev, ino;
    uint32_t user_flags;
} FileStatus;

extern char** environ;
int main(int argc, char** argv) {
    assert(argc == 2);
    setvbuf(stdout, NULL, _IONBF, 0);
    void* library = dlopen(argv[1], RTLD_LAZY|RTLD_LOCAL);
    assert(library);
    int32_t (*stat_native)(const char*, FileStatus*) = dlsym(library, "SystemNative_Stat");
    int32_t (*spawn_native)(const char*, char* const*, char* const*, const char*,
        int32_t, int32_t, int32_t, int32_t, uint32_t, uint32_t, uint32_t*, int32_t,
        int32_t*, int32_t*, int32_t*, int32_t*) = dlsym(library, "SystemNative_ForkAndExecProcess");
    assert(stat_native && spawn_native);
    char** (*get_environ)(void) = dlsym(library, "SystemNative_GetEnviron");
    char* (*get_env)(const char*) = dlsym(library, "SystemNative_GetEnv");
    assert(get_environ && get_env);
    char** env_native = get_environ();
    const char* native_path = NULL;
    unsigned env_count = 0;
    while (env_native && env_native[env_count]) {
        if (!strncmp(env_native[env_count], "PATH=", 5)) native_path = env_native[env_count]+5;
        env_count++;
    }
    printf("DOTNET_PROCESS_ENVIRON count=%u same_vector=%d PATH=%s GETENV_PATH=%s\n",
        env_count, env_native == *_NSGetEnviron(), native_path, get_env("PATH"));
    assert(native_path && get_env("PATH") && !strcmp(native_path, getenv("PATH")));

    Dl_info owner; assert(dladdr((void*)stat_native, &owner));
    printf("DOTNET_PROCESS_BACKEND %s\nPATH %s\n", owner.dli_fname, getenv("PATH"));
    const char* paths[] = {"/usr/bin/uname", "/bin/bash", "/usr/bin/true", "/usr/bin/xcrun"};
    for (unsigned i = 0; i < sizeof(paths)/sizeof(paths[0]); i++) {
        struct stat native = {0}; FileStatus pal = {0};
        errno = 0; int a = stat(paths[i], &native), ae = errno;
        errno = 0; int b = stat_native(paths[i], &pal), be = errno;
        errno = 0; int c = access(paths[i], X_OK), ce = errno;
        printf("DOTNET_PROCESS_PATH %s stat=%d errno=%d mode=%o size=%lld pal_stat=%d errno=%d mode=%o size=%lld access=%d errno=%d\n",
            paths[i], a, ae, native.st_mode, (long long)native.st_size,
            b, be, pal.mode, (long long)pal.size, c, ce);
    }
    char* child_args[] = {"/usr/bin/uname", "-s", NULL};
    int32_t pid = -1, in = -1, out = -1, err = -1;
    errno = 0;
    int status = spawn_native(child_args[0], child_args, environ, NULL, 0, 1, 1, 0, 0, 0, NULL, 0,
        &pid, &in, &out, &err);
    printf("DOTNET_PROCESS_SPAWN result=%d errno=%d pid=%d stdout=%d stderr=%d\n", status, errno, pid, out, err);
    if (status != 0) return 1;
    char buffer[256] = {0}, errors[256] = {0};
    ssize_t count = read(out, buffer, sizeof(buffer)-1), error_count = read(err, errors, sizeof(errors)-1);
    int child_status = -1;
    assert(waitpid(pid, &child_status, 0) == pid);
    printf("DOTNET_PROCESS_CHILD status=%d stdout_bytes=%ld text=%s stderr_bytes=%ld text=%s\n",
        child_status, (long)count, buffer, (long)error_count, errors);
    close(out); close(err);
    if (!WIFEXITED(child_status) || WEXITSTATUS(child_status) != 0 || count != 7 || __builtin_memcmp(buffer, "Darwin\n", 7)) return 1;
    puts("ORIGINAL_DOTNET_PROCESS_UNAME_STAT_SPAWN_AND_OUTPUT_OK");
    return 0;
}
