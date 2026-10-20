#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static uint64_t now(void) {
    struct timespec t;
    assert(clock_gettime(CLOCK_MONOTONIC, &t) == 0);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static void sleep_case(unsigned worker, unsigned index, unsigned usec) {
    printf("USLEEP_BEGIN worker=%u case=%u usec=%u\n", worker, index, usec);
    fflush(stdout);
    uint64_t before = now();
    int status = usleep(usec);
    uint64_t elapsed = now() - before;
    printf("USLEEP_END worker=%u case=%u status=%d elapsed_ns=%llu\n",
           worker, index, status, (unsigned long long)elapsed);
    fflush(stdout);
    assert(status == 0);
    assert(elapsed >= (uint64_t)usec * 900);
    assert(elapsed < 15000000000ULL);
}

static void *worker(void *context) {
    unsigned id = (unsigned)(uintptr_t)context;
    for (unsigned i = 0; i < 3; ++i) sleep_case(id, i, 250000);
    return NULL;
}

int main(void) {
    sleep_case(0, 0, 1000);
    sleep_case(0, 1, 10000);
    sleep_case(0, 2, 250000);
    sleep_case(0, 3, 250000);
    pthread_t threads[4];
    for (uintptr_t i = 0; i < 4; ++i)
        assert(pthread_create(&threads[i], NULL, worker, (void *)(i + 1)) == 0);
    for (unsigned i = 0; i < 4; ++i) assert(pthread_join(threads[i], NULL) == 0);
    puts("NATIVE_USLEEP_SERIAL_AND_FOUR_WORKERS_16_DELAYS_OK");
    return 0;
}
