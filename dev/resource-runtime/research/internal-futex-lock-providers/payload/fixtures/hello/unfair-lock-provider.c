#include <dlfcn.h>
#include <os/lock.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static os_unfair_lock lock = OS_UNFAIR_LOCK_INIT;
static unsigned long counter;
static void (*with_options)(os_unfair_lock_t, unsigned);
static void *worker(void *arg) {
    uintptr_t kind = (uintptr_t)arg;
    for (unsigned i=0; i<20000; i++) {
        if (kind & 1) with_options(&lock, 0); else os_unfair_lock_lock(&lock);
        unsigned long next = counter + 1;
        if ((i & 127) == 0) sched_yield();
        counter = next;
        os_unfair_lock_unlock(&lock);
    }
    return NULL;
}
int main(void) {
    setbuf(stdout, NULL);
    with_options = dlsym(RTLD_DEFAULT, "os_unfair_lock_lock_with_options");
    if (!with_options) return 1;
    void *providers[] = {(void*)os_unfair_lock_lock, (void*)os_unfair_lock_unlock, (void*)with_options, (void*)os_unfair_lock_trylock};
    for (unsigned i=0;i<4;i++) {
        Dl_info info;
        if (!dladdr(providers[i], &info) || !strstr(info.dli_fname, "libsystem_platform.dylib")) return 2;
        printf("LOCK_PROVIDER %u %s %s\n", i, info.dli_fname, info.dli_sname);
    }
    for (unsigned i=0;i<100;i++) {
        with_options(&lock, 0x50000);
        if (os_unfair_lock_trylock(&lock)) return 3;
        os_unfair_lock_unlock(&lock);
        if (lock._os_unfair_lock_opaque != 0 || !os_unfair_lock_trylock(&lock)) return 4;
        os_unfair_lock_unlock(&lock);
    }
    pthread_t threads[8];
    for (uintptr_t i=0;i<8;i++) if (pthread_create(&threads[i], NULL, worker, (void*)i)) return 5;
    for (unsigned i=0;i<8;i++) if (pthread_join(threads[i], NULL)) return 6;
    if (counter != 160000 || lock._os_unfair_lock_opaque) return 7;
    printf("UNFAIR_LOCK_REAL_PROVIDER_MIXED_ABI_AND_CONTENTION_OK counter=%lu\n", counter);
    return 0;
}
