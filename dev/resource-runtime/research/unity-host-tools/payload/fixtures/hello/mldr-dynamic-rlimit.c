/* Exercise the actual loader allocator with Linux descriptors and threads. */
#define main linuxcode_unused_mldr_main
#include MLDR_SOURCE_FILE
#undef main
#include <assert.h>

static unsigned completed;

static void roundtrip(int fd) {
    struct sockaddr_un address;
    socklen_t size = sizeof(address);
    assert(getsockname(fd, (struct sockaddr*)&address, &size) == 0);
    assert(address.sun_family == AF_UNIX && size > sizeof(sa_family_t));
    assert(fcntl(fd, F_GETFD) & FD_CLOEXEC);
    const char payload[] = "real-loader-socket";
    char received[sizeof(payload)];
    assert(sendto(fd, payload, sizeof(payload), 0, (struct sockaddr*)&address, size) == sizeof(payload));
    assert(recv(fd, received, sizeof(received), 0) == sizeof(received));
    assert(memcmp(payload, received, sizeof(payload)) == 0);
}

static void* worker(void* unused) {
    (void)unused;
    for (unsigned i = 0; i < 32; ++i) {
        int fd = __mldr_create_rpc_socket();
        assert(fd >= 0 && fd < 64);
        roundtrip(fd);
        __mldr_close_rpc_socket(fd);
        __atomic_fetch_add(&completed, 1, __ATOMIC_RELAXED);
    }
    return NULL;
}

int main(void) {
    struct rlimit original;
    assert(getrlimit(RLIMIT_NOFILE, &original) == 0);
    assert(original.rlim_cur >= 256);
    struct rlimit limit = original;
    limit.rlim_cur = 256;
    assert(setrlimit(RLIMIT_NOFILE, &limit) == 0);
    int high = __mldr_create_rpc_socket();
    assert(high == 255);
    roundtrip(high);

    int sentinel = open("/dev/null", O_RDONLY);
    assert(sentinel >= 0);
    assert(dup2(sentinel, 63) == 63);
    struct stat before, after;
    assert(fstat(63, &before) == 0);
    limit.rlim_cur = 64;
    assert(setrlimit(RLIMIT_NOFILE, &limit) == 0);
    int low = __mldr_create_rpc_socket();
    assert(low >= 0 && low < 63);
    roundtrip(low);
    assert(fstat(63, &after) == 0);
    assert(before.st_dev == after.st_dev && before.st_ino == after.st_ino && before.st_mode == after.st_mode);
    roundtrip(high); /* Existing sockets above the new soft limit stay usable. */
    __mldr_close_rpc_socket(low);

    pthread_t threads[8];
    for (unsigned i = 0; i < 8; ++i) assert(pthread_create(&threads[i], NULL, worker, NULL) == 0);
    for (unsigned i = 0; i < 8; ++i) assert(pthread_join(threads[i], NULL) == 0);
    assert(__atomic_load_n(&completed, __ATOMIC_RELAXED) == 256);

    int filled[64], count = 0, fd;
    while ((fd = open("/dev/null", O_RDONLY)) >= 0) filled[count++] = fd;
    assert(errno == EMFILE && count > 0);
    assert(socket_bitmap_get(&socket_bitmap) == -1 && errno == EMFILE);
    while (count) close(filled[--count]);
    limit.rlim_cur = 0;
    assert(setrlimit(RLIMIT_NOFILE, &limit) == 0);
    assert(socket_bitmap_get(&socket_bitmap) == -1 && errno == EMFILE);

    limit.rlim_cur = 256;
    assert(setrlimit(RLIMIT_NOFILE, &limit) == 0);
    __mldr_close_rpc_socket(high);
    high = __mldr_create_rpc_socket();
    assert(high == 255);
    roundtrip(high);
    __mldr_close_rpc_socket(high);
    close(63);
    close(sentinel);
    assert(setrlimit(RLIMIT_NOFILE, &original) == 0);
    printf("MLDR_DYNAMIC_RLIMIT_OK lower raise occupied retained zero exhausted concurrent_roundtrips=%u\n", __atomic_load_n(&completed, __ATOMIC_RELAXED));
    return 0;
}
