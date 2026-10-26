#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d errno=%d %s\n", __LINE__, errno, #x); return 1; } } while (0)
int main(void) {
    setbuf(stdout, NULL);
    void *h = dlopen("/usr/lib/system/libsystem_kernel.dylib", RTLD_LAZY | RTLD_LOCAL); CHECK(h);
    int (*authenticated)(int, const char *, int, int) = dlsym(h, "openat_authenticated_np");
    int (*protected_at)(int, const char *, int, int, int, ...) = dlsym(h, "openat_dprotected_np");
    int (*raw)(int, const char *, int, int, int, int, int) = dlsym(h, "__openat_dprotected_np");
    int (*protected)(const char *, int, int, int, ...) = dlsym(h, "open_dprotected_np");
    CHECK(authenticated && protected_at && raw && protected);
    char directory[] = "/tmp/linuxcode-authenticated-open-XXXXXX"; CHECK(mkdtemp(directory));
    int dfd = open(directory, O_RDONLY | O_DIRECTORY); CHECK(dfd >= 0);
    if (getenv("LINUXCODE_PROBE_PAUSE")) { printf("OPEN_PROBE_ADDRESSES public=%p raw=%p\n", protected_at, raw); sleep(25); }
    int fd = protected_at(dfd, "file", O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, -1, 0, 0600); CHECK(fd >= 0);
    CHECK(fcntl(fd, F_GETFD) & FD_CLOEXEC);
    const char expected[] = "ordinary unprotected file"; char buffer[sizeof(expected)];
    CHECK(write(fd, expected, sizeof(expected)) == sizeof(expected));
    int reader = raw(dfd, "file", O_RDONLY, -1, 0, 0, -1); CHECK(reader >= 0);
    CHECK(read(reader, buffer, sizeof(buffer)) == sizeof(buffer) && !memcmp(buffer, expected, sizeof(buffer)));
    CHECK(close(reader) == 0);
    errno = 0; CHECK(authenticated(dfd, "file", O_CREAT | O_RDONLY, -2) == -1 && errno == EINVAL);
    errno = 0; CHECK(authenticated(dfd, "file", O_RDONLY, -2) == -1 && errno == EBADF);
    errno = 0; CHECK(authenticated(dfd, "file", O_WRONLY, -1) == -1 && errno == EINVAL);
    errno = 0; CHECK(authenticated(dfd, "file", O_RDONLY, 999999) == -1 && errno == EBADF);
    errno = 0; CHECK(authenticated(dfd, "file", O_RDONLY, -1) == -1 && errno == ENOTSUP);
    errno = 0; CHECK(authenticated(dfd, "file", O_RDONLY, fd) == -1 && errno == ENOTSUP);
    errno = 0; CHECK(protected_at(dfd, "file", O_RDONLY, -1, 4) == -1 && errno == EINVAL);
    errno = 0; CHECK(protected("/tmp/no-file", O_RDONLY, -1, 4) == -1 && errno == EINVAL);
    errno = 0; CHECK(protected_at(dfd, "protected", O_CREAT | O_RDWR, 3, 0, 0600) == -1 && errno == ENOTSUP);
    CHECK(faccessat(dfd, "protected", F_OK, 0) == -1 && errno == ENOENT);
    errno = 0; CHECK(raw(dfd, "file", O_RDONLY, -1, 1, 0, -1) == -1 && errno == ENOTSUP);
    errno = 0; CHECK(raw(dfd, "file", O_RDONLY, -1, 0, 0, -2) == -1 && errno == EBADF);
    CHECK(close(fd) == 0 && unlinkat(dfd, "file", 0) == 0 && close(dfd) == 0 && rmdir(directory) == 0);
    puts("AUTHENTICATED_OPEN_WRAPPER_SEVEN_ARGUMENT_ABI_REAL_ORDINARY_IO_AND_UNSUPPORTED_ERRORS_OK");
    return 0;
}
