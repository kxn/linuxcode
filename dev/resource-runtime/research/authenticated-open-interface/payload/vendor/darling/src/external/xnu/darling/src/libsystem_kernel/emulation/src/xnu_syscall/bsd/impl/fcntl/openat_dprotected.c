#include <darling/emulation/xnu_syscall/bsd/impl/fcntl/openat.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/stat/common.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <sys/errno.h>
#include <sys/fcntl.h>

#define DP_AUTHENTICATE 4
#define DP_RAW 3
#define NO_AUTH_FD (-1)
#define DEFAULT_PROTECTION_CLASS (-1)

long sys_openat_dprotected_np(int fd, const char *path, int flags,
    int protection_class, int dpflags, unsigned int mode, int authfd)
{
    if ((dpflags & DP_AUTHENTICATE) && (flags & O_CREAT)) return -EINVAL;
    if ((dpflags & (DP_AUTHENTICATE | DP_RAW)) && (flags & (O_WRONLY | O_RDWR)))
        return -EINVAL;
    if (authfd < NO_AUTH_FD) return -EBADF;
    if (authfd != NO_AUTH_FD) {
        struct linux_stat info;
        long result = LINUX_SYSCALL(__NR_fstat, authfd, &info);
        if (result < 0) return errno_linux_to_bsd(result);
    }
    /* The Linux filesystem backend has no Darwin authenticated/data-protected
     * open operation. In particular, NO_AUTH_FD only omits the other file's
     * authentication context; it does not waive authentication of this file. */
    if (dpflags || authfd != NO_AUTH_FD ||
        ((flags & O_CREAT) && protection_class != DEFAULT_PROTECTION_CLASS))
        return -ENOTSUP;
    return sys_openat_nocancel(fd, path, flags, mode);
}
