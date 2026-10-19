#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <objc/message.h>
#include <objc/runtime.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    assert(argc == 2);
    void *handle = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!handle) { fprintf(stderr, "CS_PREF_DLOPEN_FAILED %s\n", dlerror()); return 1; }
    id *key = (id *)dlsym(handle, "SimPrefKeyPR_31199278Timeout");
    assert(key && *key && objc_getClass("NSUserDefaults"));
    id defaults = ((id (*)(id, SEL))objc_msgSend)((id)objc_getClass("NSUserDefaults"),
        sel_registerName("simulatorDefaults"));
    assert(defaults);
    long long timeout = ((long long (*)(id, SEL, id))objc_msgSend)(defaults,
        sel_registerName("integerForKey:"), *key);
    const char *text = ((const char *(*)(id, SEL))objc_msgSend)(*key, sel_registerName("UTF8String"));
    printf("CS_PREF timeout=%lld key=%s defaults_class=%s\n", timeout, text,
        class_getName(object_getClass(defaults)));
    char *(*version)(const char *) = dlsym(RTLD_DEFAULT, "launch_version_for_user_service_4coresim");
    char *(*path)(const char *) = dlsym(RTLD_DEFAULT, "launch_path_for_user_service_4coresim");
    assert(version && path);
    errno = 0;
    char *v = version("com.apple.CoreSimulator.CoreSimulatorService");
    int ve = errno;
    errno = 0;
    char *p = path("com.apple.CoreSimulator.CoreSimulatorService");
    printf("CS_SERVICE version=%s version_errno=%d path=%s path_errno=%d\n",
        v ? v : "NULL", ve, p ? p : "NULL", errno);
    free(v);
    free(p);
    puts("CORE_SIMULATOR_ACTUAL_PREFERENCES_AND_SERVICE_QUERY_COMPLETED");
    return 0;
}
