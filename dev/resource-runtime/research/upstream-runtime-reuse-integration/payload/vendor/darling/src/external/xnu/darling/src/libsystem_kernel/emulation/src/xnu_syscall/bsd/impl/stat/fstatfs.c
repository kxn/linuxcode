#include <darling/emulation/xnu_syscall/bsd/impl/stat/fstatfs.h>
#include <sys/errno.h>
#include <darling/emulation/conversion/stat/common.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/common/simple.h>
#include <darling/emulation/xnu_syscall/bsd/helper/stat/mounts.h>
#undef memset
extern void *memset(void *,int,__SIZE_TYPE__);
long sys_fstatfs(int fd,struct bsd_statfs *buf)
{
#ifdef __x86_64__
    return sys_fstatfs64(fd,(struct bsd_statfs64 *)buf);
#else
    return -ENOTSUP;
#endif
}
long sys_fstatfs64(int fd,struct bsd_statfs64 *buf)
{
    if(!buf)return -EFAULT;
    struct linux_statfs64 fs;struct linux_stat identity;
    long result=LINUX_SYSCALL(__NR_fstatfs,fd,&fs);
    if(result<0)return errno_linux_to_bsd(result);
    result=LINUX_SYSCALL(__NR_fstat,fd,&identity);
    if(result<0)return errno_linux_to_bsd(result);
    memset(buf,0,sizeof(*buf));statfs_linux_to_bsd64(&fs,buf);
    buf->f_fsid=darling_statfs_fsid(identity.st_dev,fs.f_type);buf->f_iosize=fs.f_bsize;
    /* Mount records use Linux physical paths. fdpath() already returns a
     * Darwin path and must not be compared with this table. readlink also
     * permits fstatfs on an open-but-unlinked file. */
    char descriptor[64],physical[4096];
    __simple_snprintf(descriptor,sizeof(descriptor),"/proc/self/fd/%d",fd);
    result=LINUX_SYSCALL(__NR_readlink,descriptor,physical,sizeof(physical)-1);
    if(result<0)return errno_linux_to_bsd(result);
    physical[result]=0;
    struct darling_mount_reader reader;struct darling_mount_entry entry;
    result=darling_mount_open(&reader);if(result<0)return errno_linux_to_bsd(result);
    size_t longest=0;
    while((result=darling_mount_next(&reader,&entry))>0) {
        size_t n=strlen(entry.target);
        if(n<longest||!darling_mount_contains(entry.target,physical))continue;
        result=darling_mount_guest_name(buf->f_mntonname,sizeof(buf->f_mntonname),entry.target);
        if(result<0)break;
        if(entry.source[0]=='/')result=darling_mount_guest_name(buf->f_mntfromname,sizeof(buf->f_mntfromname),entry.source);
        else if(strlcpy(buf->f_mntfromname,entry.source,sizeof(buf->f_mntfromname))>=sizeof(buf->f_mntfromname))result=-36;
        if(result<0)break;
        strlcpy(buf->f_fstypename,entry.type,sizeof(buf->f_fstypename));longest=n;
    }
    LINUX_SYSCALL(__NR_close,reader.fd);
    if(result<0)return errno_linux_to_bsd(result);
    if(buf->f_mntonname[0]=='/' && !buf->f_mntonname[1])buf->f_flags|=0x00004000; /* MNT_ROOTFS */
    return longest?0:-ENOENT;
}
