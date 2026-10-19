#include <assert.h>
#include <dirent.h>
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Public .NET coreclr hosting ABI, not a replacement for the runtime. */
typedef int (*initialize_fn)(const char*, const char*, int, const char**, const char**, void**, unsigned int*);
typedef int (*execute_fn)(void*, unsigned int, int, const char**, const char*, unsigned int*);
typedef int (*shutdown_fn)(void*, unsigned int, int*);

int main(int argc, char** argv) {
    assert(argc == 3);
    setvbuf(stdout, NULL, _IONBF, 0);
    const char* deploy = argv[1];
    char runtime[PATH_MAX];
    assert(snprintf(runtime, sizeof(runtime), "%s/libcoreclr.dylib", deploy) < sizeof(runtime));
    void* library = dlopen(runtime, RTLD_LAZY|RTLD_GLOBAL);
    if (!library) fprintf(stderr, "%s\n", dlerror());
    assert(library);
    initialize_fn initialize = dlsym(library, "coreclr_initialize");
    execute_fn execute = dlsym(library, "coreclr_execute_assembly");
    shutdown_fn shutdown = dlsym(library, "coreclr_shutdown_2");
    assert(initialize && execute && shutdown);
    char* tpa = calloc(1, 1024*1024);
    assert(tpa);
    size_t used = 0;
    DIR* dir = opendir(deploy); assert(dir);
    struct dirent* entry;
    while ((entry = readdir(dir))) {
        size_t len = strlen(entry->d_name);
        if (len < 4 || strcmp(entry->d_name+len-4, ".dll")) continue;
        int count = snprintf(tpa+used, 1024*1024-used, "%s%s/%s", used ? ":" : "", deploy, entry->d_name);
        assert(count > 0 && count < 1024*1024-used); used += count;
    }
    closedir(dir);
    const char* keys[] = {"TRUSTED_PLATFORM_ASSEMBLIES", "APP_PATHS", "NATIVE_DLL_SEARCH_DIRECTORIES", "System.Globalization.Invariant"};
    const char* values[] = {tpa, deploy, deploy, "true"};
    void* host = NULL; unsigned int domain = 0;
    int result = initialize(argv[0], "LinuxcodeManagedEnvironmentProbe", 4, keys, values, &host, &domain);
    printf("CORECLR_INITIALIZE %x\n", result);
    if (result < 0) return 1;
    unsigned int exit_code = 255;
    result = execute(host, domain, 0, NULL, argv[2], &exit_code);
    printf("CORECLR_EXECUTE %x MANAGED_EXIT %u\n", result, exit_code);
    int latched = -1;
    int closed = shutdown(host, domain, &latched);
    printf("CORECLR_SHUTDOWN %x LATCHED_EXIT %d\n", closed, latched);
    free(tpa);
    return result == 0 && exit_code == 0 && closed == 0 ? 0 : 1;
}
