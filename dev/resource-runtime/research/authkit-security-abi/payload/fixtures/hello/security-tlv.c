#define _DARWIN_C_SOURCE 1
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct descriptor {
    void *(*thunk)(struct descriptor *);
    uintptr_t key;
    uintptr_t offset;
};
static struct descriptor *descriptors[2];
static size_t expected_offsets[2], template_size;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static int ready, released;
struct observation { void *base; int failed; };

static void *observe(void *argument) {
    struct observation *result = argument;
    void *first[2] = {NULL, NULL};
    for (int iteration = 0; iteration < 256; ++iteration) {
        for (int i = 0; i < 2; ++i) {
            void *address = descriptors[i]->thunk(descriptors[i]);
            if (!address) { result->failed = 1; continue; }
            if (iteration == 0) first[i] = address;
            if (address != first[i]) result->failed = 1;
        }
    }
    if (!first[0] || !first[1]) result->failed = 1;
    else {
        result->base = (char *)first[0]-expected_offsets[0];
        if ((char *)first[1]-expected_offsets[1] != result->base) result->failed = 1;
        for (size_t i = 0; i < template_size; ++i)
            if (((unsigned char *)result->base)[i]) result->failed = 1;
    }
    pthread_mutex_lock(&lock);
    ++ready;
    pthread_cond_broadcast(&condition);
    while (!released) pthread_cond_wait(&condition, &lock);
    pthread_mutex_unlock(&lock);
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 7) return 2;
    void *handle = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!handle) { fprintf(stderr, "SECURITY_DLOPEN_ERROR %s\n", dlerror()); return 3; }
    void *anchor = dlsym(handle, "kSecClass");
    Dl_info image, handler;
    if (!anchor || !dladdr(anchor, &image)) return 4;
    printf("SECURITY_TLV_IMAGE %s\n", image.dli_fname);
    void *aliases = dlopen("/usr/lib/libDarlingSecuritySessionValues.dylib", RTLD_LAZY | RTLD_LOCAL);
    if (!aliases) return 11;
    const char *classes[] = {"SecSessionInfo", "SecExternalPreSharedKey", "ExternalPreSharedKey", "SecOfferedEPSK", "OfferedEPSK"};
    for (int i = 0; i < 5; ++i) {
        for (int meta = 0; meta < 2; ++meta) {
            char name[160];
            snprintf(name, sizeof(name), "OBJC_%s_$_%s", meta ? "METACLASS" : "CLASS", classes[i]);
            void *original = dlsym(handle, name), *forwarded = dlsym(aliases, name);
            Dl_info owner;
            if (!original || original != forwarded || !dladdr(original, &owner) ||
                strcmp(owner.dli_fname, image.dli_fname)) return 12;
        }
    }
    puts("ORIGINAL_SECURITY_SESSION_CLASS_IDENTITY_VERIFIED symbols=10");
    template_size = strtoull(argv[6], NULL, 0);
    if (template_size != 64) return 5;
    for (int i = 0; i < 2; ++i) {
        uintptr_t offset = strtoull(argv[2+2*i], NULL, 0);
        expected_offsets[i] = strtoull(argv[3+2*i], NULL, 0);
        descriptors[i] = (struct descriptor *)((char *)image.dli_fbase+offset);
        if (!descriptors[i]->thunk || descriptors[i]->offset != expected_offsets[i]) return 6;
    }
    if (descriptors[0]->thunk != descriptors[1]->thunk || descriptors[0]->key != descriptors[1]->key) return 7;
    if (!dladdr((void *)descriptors[0]->thunk, &handler)) return 8;
    printf("SECURITY_TLV_HANDLER %s\n", handler.dli_fname);
    pthread_t threads[4];
    struct observation results[4] = {{0}};
    for (int i = 0; i < 4; ++i)
        if (pthread_create(&threads[i], NULL, observe, &results[i])) return 9;
    pthread_mutex_lock(&lock);
    while (ready != 4) pthread_cond_wait(&condition, &lock);
    int failed = 0;
    for (int i = 0; i < 4; ++i) {
        failed |= results[i].failed;
        for (int j = 0; j < i; ++j)
            if (results[i].base == results[j].base) failed = 1;
    }
    released = 1;
    pthread_cond_broadcast(&condition);
    pthread_mutex_unlock(&lock);
    for (int i = 0; i < 4; ++i) pthread_join(threads[i], NULL);
    if (failed) return 10;
    puts("ORIGINAL_SECURITY_TLS_VERIFIED threads=4 descriptors=2 queries=2048 zero_fill=64");
    return 0;
}
