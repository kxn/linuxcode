#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d %s\n", __LINE__, #x); return 1; } } while (0)
#define COOPERATIVE 0x08000000ul
typedef unsigned long priority_t;
static unsigned completed, errors, cooperative_count, legacy_count;
static priority_t expected;
static uint64_t checksum;
static pthread_t workers[256];
static void worker(priority_t pp) {
    priority_t tsd;
    __asm__("movq %%gs:32,%0" : "=r" (tsd));
    unsigned index = __atomic_load_n(&completed, __ATOMIC_RELAXED);
    if (pp != expected || tsd != (expected & ~COOPERATIVE))
        __atomic_fetch_add(&errors, 1, __ATOMIC_RELAXED);
    if (pp & COOPERATIVE) ++cooperative_count; else ++legacy_count;
    workers[index] = pthread_self();
    uint64_t value = 0;
    for (unsigned i = 1; i <= 10000; ++i) value += (uint64_t)i * i;
    checksum += value;
    __atomic_fetch_add(&completed, 1, __ATOMIC_RELEASE);
}
int main(void) {
    setbuf(stdout, NULL);
    void *h = dlopen("/usr/lib/system/libsystem_pthread.dylib", RTLD_LAZY | RTLD_LOCAL);
    CHECK(h);
    int (*cooperative)(int, priority_t) = dlsym(h, "_pthread_workqueue_add_cooperativethreads");
    int (*legacy)(int, priority_t) = dlsym(h, "_pthread_workqueue_addthreads");
    int (*initialize)(void (*)(priority_t), int, int) = dlsym(h, "_pthread_workqueue_init");
    priority_t (*encode)(unsigned, int, unsigned long) = dlsym(h, "_pthread_qos_class_encode");
    CHECK(cooperative && legacy && initialize && encode);
    CHECK(cooperative(1, 0) == EPERM);
    CHECK(legacy(1, 0) == EPERM);
    CHECK(initialize(worker, 0, 0) == 0);
    CHECK(initialize(worker, 0, 0) == EBUSY);
    for (unsigned i = 0; i < 256; ++i) {
        priority_t pp = encode(i & 2 ? 0x11 : 0x15, 0, 0);
        expected = pp | (i & 1 ? COOPERATIVE : 0);
        CHECK((i & 1 ? cooperative : legacy)(1, pp) == 0);
        for (unsigned spins = 0; __atomic_load_n(&completed, __ATOMIC_ACQUIRE) != i + 1; ++spins) {
            CHECK(spins < 30000);
            usleep(1000);
        }
        usleep(1000);
    }
    CHECK(errors == 0 && cooperative_count == 128 && legacy_count == 128);
    CHECK(checksum == 256ull * 333383335000ull);
    unsigned reused = 0;
    for (unsigned i = 1; i < 256; ++i) if (workers[i] == workers[i - 1]) ++reused;
    CHECK(reused > 0);
    printf("COOPERATIVE_WORKQUEUE_REAL_CALLBACK_QOS_TSD_AND_REUSE_OK callbacks=%u reused=%u\n", completed, reused);
    return 0;
}
