#include <uuid/uuid.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

_Static_assert(sizeof(uuid_t) == 16, "Darwin UUID ABI");
int main(int argc, char **argv) {
    if (argc != 3) return 10;
    void *system = dlopen("/usr/lib/libSystem.B.dylib", RTLD_NOW);
    if (!system) return 11;
    const unsigned char *id = dlsym(system, "ne_privacy_dns_netagent_id");
    if (!id) { puts("NE_AGENT_UUID_MISSING"); return 12; }
    if ((uintptr_t)id % 16 || dlsym(RTLD_DEFAULT,"ne_privacy_dns_netagent_id") != id) return 13;
    Dl_info owner;
    if (!dladdr(id,&owner) || !owner.dli_fname || !strstr(owner.dli_fname,argv[1])) return 14;
    uuid_t expected;
    if (uuid_parse(argv[2],expected) || uuid_compare(id,expected)) return 15;
    uuid_string_t text; uuid_unparse_upper(id,text);
    if (strcmp(text,argv[2])) return 16;
    pid_t child = fork(); if (child < 0) return 17;
    if (!child) {
        signal(SIGSEGV,SIG_DFL); signal(SIGBUS,SIG_DFL);
        *(volatile unsigned char *)(uintptr_t)id ^= 1;
        _exit(18);
    }
    int status;
    if (waitpid(child,&status,0) != child || !WIFSIGNALED(status) ||
        (WTERMSIG(status) != SIGSEGV && WTERMSIG(status) != SIGBUS)) return 19;
    printf("NE_AGENT_UUID_VALUE %s\n",text);
    printf("NE_AGENT_UUID_PROVIDER %s\n",owner.dli_fname);
    puts("NE_AGENT_ORIGINAL_UUID_BYTES_IDENTITY_PROVIDER_AND_READONLY_OK");
    return 0;
}
