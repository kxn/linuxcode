#include <darling/emulation/xnu_syscall/bsd/impl/stat/statfs.h>
#include <darling/emulation/xnu_syscall/bsd/impl/stat/fstatfs.h>
#include <sys/errno.h>
#include <darling/emulation/conversion/stat/common.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/fcntl/open.h>
#include <darling/emulation/linux_premigration/vchroot_expand.h>
#include <darling/emulation/common/bsdthread/per_thread_wd.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#undef strlcpy
extern __SIZE_TYPE__ strlcpy(char *,const char *,__SIZE_TYPE__);
long sys_statfs(const char *path,struct bsd_statfs *buf)
{
#ifdef __x86_64__
    return sys_statfs64(path,(struct bsd_statfs64 *)buf);
#else
    return -ENOTSUP;
#endif
}
long sys_statfs64(const char *path,struct bsd_statfs64 *buf)
{
    if(!path||!buf)return -EFAULT;
    struct vchroot_expand_args vc;
    vc.flags=VCHROOT_FOLLOW;vc.dfd=get_perthread_wd();
    if(strlcpy(vc.path,path,sizeof(vc.path))>=sizeof(vc.path))return -ENAMETOOLONG;
    long result=vchroot_expand(&vc);
    if(result<0)return errno_linux_to_bsd(result);
    /* O_PATH preserves statfs permission semantics, including unreadable files
     * and directories. Opening the resolved vnode also keeps path and FD
     * filesystem identities/mount names on the very same implementation. */
    int fd=LINUX_SYSCALL(__NR_openat,vc.dfd,vc.path,0x200000|LINUX_O_CLOEXEC,0);
    if(fd<0)return errno_linux_to_bsd(fd);
    result=sys_fstatfs64(fd,buf);LINUX_SYSCALL(__NR_close,fd);return result;
}
