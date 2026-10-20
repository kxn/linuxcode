#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#define STORAGE_BYTES 16384
int main(int argc, char **argv) {
    if (argc != 2) return 10;
    void *system = dlopen("/usr/lib/libSystem.B.dylib", RTLD_NOW);
    if (!system) return 11;
    unsigned char *p = dlsym(system, "os_script_config_storage");
    if (!p) { puts("SCRIPT_CONFIG_MISSING"); return 12; }
    if ((uintptr_t)p < 0x100000000ULL || (uintptr_t)p % 4096 || getpagesize() != 4096) return 13;
    if (dlsym(RTLD_DEFAULT, "os_script_config_storage") != p) return 14;
    Dl_info owner;
    if (!dladdr(p, &owner) || !owner.dli_fname || !strstr(owner.dli_fname, argv[1])) return 15;
    for (int i = 0; i < STORAGE_BYTES; ++i) if (p[i]) return 16;
    for (int i = 0; i < STORAGE_BYTES; ++i) p[i] = (unsigned char)(i * 37 + 19);
    for (int i = 0; i < STORAGE_BYTES; ++i) if (p[i] != (unsigned char)(i * 37 + 19)) return 17;
    pid_t child = fork();
    if (child < 0) return 18;
    if (!child) { memset(p, 0xa5, STORAGE_BYTES); _exit(p[0] == 0xa5 ? 0 : 1); }
    int status;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status)) return 19;
    for (int i = 0; i < STORAGE_BYTES; ++i) if (p[i] != (unsigned char)(i * 37 + 19)) return 20;
    for (int page = 0; page < 4; ++page) {
        child = fork();
        if (child < 0) return 21;
        if (!child) {
            signal(SIGSEGV, SIG_DFL); signal(SIGBUS, SIG_DFL);
            if (mprotect(p, STORAGE_BYTES, PROT_READ)) _exit(22);
            volatile unsigned char *cell = p + page * 4096;
            if (*cell != (unsigned char)(page * 4096 * 37 + 19)) _exit(23);
            *cell = 42;
            _exit(24);
        }
        if (waitpid(child, &status, 0) != child || !WIFSIGNALED(status) ||
            (WTERMSIG(status) != SIGSEGV && WTERMSIG(status) != SIGBUS)) return 25;
    }
    printf("SCRIPT_CONFIG_PROVIDER %s\n", owner.dli_fname);
    puts("SCRIPT_CONFIG_ZERO_16384_ALIGNMENT_IDENTITY_COW_AND_FOUR_READONLY_PAGES_OK");
    return 0;
}
