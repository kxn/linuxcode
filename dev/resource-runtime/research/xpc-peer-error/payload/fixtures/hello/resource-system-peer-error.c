#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int rich_error_existing_probe_main(int argc, char **argv);

int main(int argc, char **argv) {
    assert(argc == 3);
    void *system = dlopen("/usr/lib/libSystem.B.dylib", RTLD_NOW | RTLD_LOCAL | RTLD_FIRST);
    assert(system);
    void *peer = dlsym(system, "_xpc_error_peer_code_signing_requirement");
    if (!strcmp(argv[2], "missing")) {
        assert(!peer);
        puts("RESOURCE_SYSTEM_PEER_ERROR_ABSENT_CONTROL_OK");
        return 0;
    }
    assert(!strcmp(argv[2], "present") && peer);
    void *provider = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL | RTLD_FIRST);
    assert(provider && peer == dlsym(provider, "_xpc_error_peer_code_signing_requirement"));
    int status = rich_error_existing_probe_main(2, argv);
    assert(status == 0);
    puts("RESOURCE_SYSTEM_PEER_ERROR_REEXPORT_IDENTITY_AND_REAL_OBJECTS_OK");
    return 0;
}
