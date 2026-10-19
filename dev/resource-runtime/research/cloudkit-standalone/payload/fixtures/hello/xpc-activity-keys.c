#include <assert.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <xpc/xpc.h>
#include "activity-keys.h"

int main(int argc, char **argv) {
    assert(argc == 2);
    bool missing = !strcmp(argv[1], "missing");
    assert(missing || !strcmp(argv[1], "present"));
    void *system = dlopen("/usr/lib/libSystem.B.dylib", RTLD_LAZY | RTLD_LOCAL | RTLD_FIRST);
    void *backend = dlopen("/usr/lib/system/libxpc.dylib", RTLD_LAZY | RTLD_LOCAL | RTLD_FIRST);
    assert(system && backend);
    Dl_info implementation;
    assert(dladdr(dlsym(backend, "xpc_dictionary_create"), &implementation));
    const uint64_t values[] = {0, 1, UINT64_MAX};
    unsigned checked = 0, absent = 0;
    for (unsigned i = 0; i < sizeof(activity_keys)/sizeof(activity_keys[0]); i++) {
        const struct ActivityKey *key = &activity_keys[i];
        const char *const *slot = dlsym(system, key->symbol);
        if (missing && key->added) {
            assert(!slot && !dlsym(backend, key->symbol));
            absent++;
            continue;
        }
        assert(slot && slot == dlsym(backend, key->symbol));
        Dl_info owner;
        assert(dladdr(slot, &owner) && owner.dli_fbase == implementation.dli_fbase);
        assert(*slot && !strcmp(*slot, key->value));
        for (unsigned j = 0; j < sizeof(values)/sizeof(values[0]); j++) {
            char temporary[256];
            assert(strlen(*slot) < sizeof(temporary));
            strcpy(temporary, *slot);
            xpc_object_t criteria = xpc_dictionary_create(NULL, NULL, 0);
            assert(criteria && xpc_get_type(criteria) == XPC_TYPE_DICTIONARY);
            xpc_dictionary_set_uint64(criteria, temporary, values[j]);
            memset(temporary, '?', strlen(temporary));
            assert(xpc_dictionary_get_uint64(criteria, key->value) == values[j]);
            xpc_object_t copy = xpc_copy(criteria);
            assert(copy && copy != criteria);
            xpc_dictionary_set_uint64(copy, key->value, values[j] ^ 1);
            assert(xpc_dictionary_get_uint64(criteria, key->value) == values[j]);
            assert(xpc_dictionary_get_uint64(copy, key->value) == (values[j] ^ 1));
            xpc_release(copy);
            xpc_release(criteria);
            checked++;
        }
    }
    if (missing) {
        assert(absent == 1);
        puts("XPC_ACTIVITY_UPLOAD_KEY_ABSENT_CONTROL_OK");
    } else {
        assert(!absent);
        printf("XPC_ACTIVITY_KEYS_AND_CRITERIA_OK keys=%zu values=%u\n",
               sizeof(activity_keys)/sizeof(activity_keys[0]), checked);
    }
    return 0;
}
