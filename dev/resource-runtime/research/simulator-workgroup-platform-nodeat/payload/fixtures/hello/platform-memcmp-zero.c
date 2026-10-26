#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#ifdef NATIVE_DARWIN
#include <dlfcn.h>
static unsigned long (*compare_zero)(const void *, size_t);
#else
extern unsigned long _platform_memcmp_zero_aligned8(const void *, size_t);
#define compare_zero _platform_memcmp_zero_aligned8
#endif
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d %s\n", __LINE__, #x); return 1; } } while (0)
static unsigned checks;
static int verify(unsigned char *s, size_t n) {
    unsigned long expected = 0;
    for (size_t i = 0; i < n; ++i) expected |= s[i];
    ++checks;
    return compare_zero(s, n) == (expected != 0);
}
int main(void) {
    setbuf(stdout, NULL);
#ifdef NATIVE_DARWIN
    void *h = dlopen("/usr/lib/system/libsystem_platform.dylib", RTLD_LAZY | RTLD_LOCAL);
    CHECK(h); compare_zero = dlsym(h, "_platform_memcmp_zero_aligned8"); CHECK(compare_zero);
#endif
    CHECK(compare_zero(NULL, 0) == 0);
    size_t page = (size_t)getpagesize(), capacity = page * 8;
    unsigned char *map = mmap(NULL, capacity + 2 * page, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    CHECK(map != MAP_FAILED); unsigned char *base = map + page;
    CHECK(mprotect(base, capacity, PROT_READ | PROT_WRITE) == 0);
    for (size_t n = 8; n <= 1024; n += 8) {
        for (size_t offset = 0; offset < 64; offset += 8) {
            unsigned char *s = base + offset; memset(base, 0, capacity);
            CHECK(verify(s, n));
            for (size_t i = 0; i < n; ++i) { s[i] = (unsigned char)(1u << (i % 8)); CHECK(verify(s, n)); s[i] = 0; }
            s[n] = 255; CHECK(verify(s, n)); s[n] = 0;
            if (offset) { s[-1] = 255; CHECK(verify(s, n)); s[-1] = 0; }
        }
    }
    for (size_t n = 8; n <= capacity; n += 8) {
        unsigned char *s = base + capacity - n; memset(base, 0, capacity);
        CHECK(verify(s, n)); s[n - 1] = 128; CHECK(verify(s, n)); s[n - 1] = 0;
        s[0] = 255; CHECK(verify(s, n)); s[0] = 0;
    }
    CHECK(munmap(map, capacity + 2 * page) == 0);
    printf("PLATFORM_MEMCMP_ZERO_ALIGNED8_BOUNDARIES_AND_ALL_BYTE_POSITIONS_OK checks=%u\n", checks);
    return 0;
}
