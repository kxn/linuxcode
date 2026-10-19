#include <assert.h>
#include <errno.h>
#include <mach/mach_time.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static uint64_t monotonic(void) {
    struct timespec t;
    assert(clock_gettime(CLOCK_MONOTONIC, &t) == 0);
    assert(t.tv_nsec >= 0 && t.tv_nsec < 1000000000);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

int main(int argc, char **argv) {
    assert(argc == 2);
    long long expected = strtoll(argv[1], NULL, 10);
    size_t size = 0;
    assert(sysctlbyname("kern.boottime", NULL, &size, NULL, 0) == 0);
    assert(size == sizeof(struct timeval));
    struct { uint64_t before; struct timeval value; uint64_t after; } guarded;
    memset(&guarded, 0xa5, sizeof(guarded));
    size = sizeof(guarded.value)-1;
    errno = 0;
    assert(sysctlbyname("kern.boottime", &guarded.value, &size, NULL, 0) == -1);
    assert(errno != 0 && guarded.before == 0xa5a5a5a5a5a5a5a5ULL && guarded.after == guarded.before);
    mach_timebase_info_data_t timebase;
    assert(mach_timebase_info(&timebase) == 0 && timebase.numer && timebase.denom);
    uint64_t first = monotonic(), previous = first, raw = mach_absolute_time();
    for (unsigned i = 0; i < 96; ++i) {
        size = sizeof(guarded.value);
        assert(sysctlbyname("kern.boottime", &guarded.value, &size, NULL, 0) == 0);
        printf("BOOT_SAMPLE %u epoch=%lld usec=%d expected=%lld\n", i,
               (long long)guarded.value.tv_sec, guarded.value.tv_usec, expected);
        fflush(stdout);
        assert(size == sizeof(guarded.value) && guarded.value.tv_sec == expected && guarded.value.tv_usec == 0);
        assert(guarded.before == 0xa5a5a5a5a5a5a5a5ULL && guarded.after == guarded.before);
        assert(usleep(25000) == 0);
        uint64_t current = monotonic();
        assert(current >= previous);
        previous = current;
    }
    uint64_t raw_ns = (mach_absolute_time()-raw) * timebase.numer / timebase.denom;
    uint64_t delta = previous-first;
    uint64_t difference = delta > raw_ns ? delta-raw_ns : raw_ns-delta;
    printf("CLOCK_CROSSCHECK monotonic_ns=%llu mach_ns=%llu difference_ns=%llu\n",
           (unsigned long long)delta, (unsigned long long)raw_ns, (unsigned long long)difference);
    assert(delta > 2000000000ULL && difference < 25000000ULL);
    puts("KERN_BOOTTIME_LINUX_EPOCH_96_SAMPLES_BUFFER_GUARDS_AND_MONOTONIC_MACH_CLOCK_OK");
    return 0;
}
