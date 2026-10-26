#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d errno=%d %s\n", __LINE__, errno, #x); return 1; } } while (0)
int main(void) {
    setbuf(stdout, NULL);
    void *h = dlopen("/usr/lib/system/libsystem_kernel.dylib", RTLD_LAZY | RTLD_LOCAL); CHECK(h);
    int (*create)(int, const char *, mode_t) = dlsym(h, "mkfifoat"); CHECK(create);
    int (*node)(int, const char *, mode_t, unsigned int) = dlsym(h, "mknodat"); CHECK(node);
    char directory[] = "/tmp/linuxcode-mkfifoat-XXXXXX"; CHECK(mkdtemp(directory));
    int dfd = open(directory, O_RDONLY | O_DIRECTORY); CHECK(dfd >= 0);
    mode_t previous = umask(0027);
    CHECK(create(dfd, "pipe", S_IFDIR | 0666) == 0);
    struct stat st; CHECK(fstatat(dfd, "pipe", &st, AT_SYMLINK_NOFOLLOW) == 0);
    CHECK(S_ISFIFO(st.st_mode) && (st.st_mode & 0777) == 0640);
    int fd = openat(dfd, "pipe", O_RDWR | O_NONBLOCK); CHECK(fd >= 0);
    const char message[] = "real Linux FIFO bytes"; char received[sizeof(message)];
    CHECK(write(fd, message, sizeof(message)) == sizeof(message));
    CHECK(read(fd, received, sizeof(received)) == sizeof(received));
    CHECK(!memcmp(received, message, sizeof(message))); CHECK(close(fd) == 0);
    errno = 0; CHECK(create(dfd, "pipe", 0600) == -1 && errno == EEXIST);
    errno = 0; CHECK(create(-9, "relative", 0600) == -1 && errno == EBADF);
    errno = 0; CHECK(create(dfd, "missing/pipe", 0600) == -1 && errno == ENOENT);
    errno = 0; CHECK(create(dfd, "", 0600) == -1 && errno == ENOENT);
    errno = 0; CHECK(create(dfd, NULL, 0600) == -1 && errno == EFAULT);
    errno = 0; CHECK(create(dfd, (const char *)1, 0600) == -1 && errno == EFAULT);
    char longpath[1100]; memset(longpath, 'x', sizeof(longpath)); longpath[sizeof(longpath) - 1] = 0;
    errno = 0; CHECK(create(dfd, longpath, 0600) == -1 && errno == ENAMETOOLONG);
    char absolute[1024]; snprintf(absolute, sizeof(absolute), "%s/absolute", directory);
    CHECK(create(-9, absolute, 0600) == 0);
    CHECK(fstatat(dfd, "absolute", &st, AT_SYMLINK_NOFOLLOW) == 0 && S_ISFIFO(st.st_mode));
    int regular = openat(dfd, "file", O_CREAT | O_WRONLY, 0600); CHECK(regular >= 0);
    errno = 0; CHECK(create(regular, "pipe", 0600) == -1 && errno == ENOTDIR);
    CHECK(close(regular) == 0);
    CHECK(node(dfd, "node-pipe", S_IFIFO | 0660, 0x12345678) == 0);
    CHECK(fstatat(dfd, "node-pipe", &st, AT_SYMLINK_NOFOLLOW) == 0 && S_ISFIFO(st.st_mode));
    fd = openat(dfd, "node-pipe", O_RDWR | O_NONBLOCK); CHECK(fd >= 0);
    CHECK(write(fd, message, sizeof(message)) == sizeof(message));
    CHECK(read(fd, received, sizeof(received)) == sizeof(received) && !memcmp(received, message, sizeof(message)));
    CHECK(close(fd) == 0 && unlinkat(dfd, "node-pipe", 0) == 0);
    CHECK(unlinkat(dfd, "pipe", 0) == 0 && unlinkat(dfd, "absolute", 0) == 0 && unlinkat(dfd, "file", 0) == 0);
    CHECK(close(dfd) == 0 && rmdir(directory) == 0); umask(previous);
    puts("MKFIFOAT_REAL_FIFO_BYTES_DIRFD_MODE_UMASK_AND_ERROR_CONTRACT_OK");
    return 0;
}
