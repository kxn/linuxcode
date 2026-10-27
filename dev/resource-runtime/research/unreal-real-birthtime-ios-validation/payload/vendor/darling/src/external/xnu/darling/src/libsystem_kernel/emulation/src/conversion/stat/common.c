// This is needed so stat is not stat64
#define _DARWIN_NO_64_BIT_INODE

// NOTE: in this case, platform-include/sys/stat.h is used
#include <sys/stat.h>

#include <darling/emulation/conversion/stat/common.h>
#include <darling/emulation/conversion/stat/mount_flags.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/getuid.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/getgid.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/xnu_syscall/bsd/helper/xattr/metadata_linux.h>

void stat_linux_to_bsd(const struct linux_stat* lstat, struct stat* stat)
{
	__builtin_memset(stat, 0, sizeof(*stat));
	stat->st_dev = lstat->st_dev;
	stat->st_mode = lstat->st_mode;
	stat->st_nlink = lstat->st_nlink;
	stat->st_ino = lstat->st_ino;
	stat->st_uid = /*lstat->st_uid*/ sys_getuid();
	stat->st_gid = /*lstat->st_gid*/ sys_getgid();
	stat->st_rdev = lstat->st_rdev;
	stat->st_size = lstat->st_size;
	stat->st_blksize = lstat->st_blksize;
	stat->st_blocks = lstat->st_blocks;
	stat->st_atimespec.tv_sec = lstat->st_atime;
	stat->st_atimespec.tv_nsec = lstat->st_atime_nsec;
	stat->st_mtimespec.tv_sec = lstat->st_mtime;
	stat->st_mtimespec.tv_nsec = lstat->st_mtime_nsec;
	stat->st_ctimespec.tv_sec = lstat->st_ctime;
	stat->st_ctimespec.tv_nsec = lstat->st_ctime_nsec;
	stat->st_flags = 0;
}

void stat_linux_to_bsd64(const struct linux_stat* lstat, struct stat64* stat)
{
	__builtin_memset(stat, 0, sizeof(*stat));
	stat->st_dev = lstat->st_dev;
	stat->st_mode = lstat->st_mode;
	stat->st_nlink = lstat->st_nlink;
	stat->st_ino = lstat->st_ino;
	stat->st_uid = /*lstat->st_uid*/ sys_getuid();
	stat->st_gid = /*lstat->st_gid*/ sys_getgid();
	stat->st_rdev = lstat->st_rdev;
	stat->st_size = lstat->st_size;
	stat->st_blksize = lstat->st_blksize;
	stat->st_blocks = lstat->st_blocks;
	stat->st_atimespec.tv_sec = lstat->st_atime;
	stat->st_atimespec.tv_nsec = lstat->st_atime_nsec;
	stat->st_mtimespec.tv_sec = lstat->st_mtime;
	stat->st_mtimespec.tv_nsec = lstat->st_mtime_nsec;
	stat->st_ctimespec.tv_sec = lstat->st_ctime;
	stat->st_ctimespec.tv_nsec = lstat->st_ctime_nsec;
	stat->st_flags = 0;
}

/* Legacy Linux stat has no birth time. Ask statx for the genuine value;
 * leave the initialized zero when the filesystem/kernel does not supply it. */
void stat_birthtime_linux_to_bsd64(int fd, const char* path, int flags, struct stat64* stat)
{
#ifdef __NR_statx
	struct metadata_linux_statx sx = {0};
	long result = LINUX_SYSCALL(__NR_statx, fd, path, flags, 0x800, &sx);
	if (result == 0 && (sx.mask & 0x800)) {
		stat->st_birthtimespec.tv_sec = sx.btime.sec;
		stat->st_birthtimespec.tv_nsec = sx.btime.nsec;
	}
#endif
}

void statfs_linux_to_bsd(const struct linux_statfs64* lstat, struct bsd_statfs* stat)
{
	stat->f_type = lstat->f_type;
	stat->f_bsize = lstat->f_bsize;
	stat->f_blocks = lstat->f_blocks;
	stat->f_bfree = lstat->f_bfree;
	stat->f_bavail = lstat->f_bavail;
	stat->f_files = lstat->f_files;
	stat->f_ffree = lstat->f_ffree;
	stat->f_fsid = lstat->f_fsid;
	stat->f_flags = darling_mount_flags_to_bsd(lstat->f_flags, lstat->f_type);
}

void statfs_linux_to_bsd64(const struct linux_statfs64* lstat, struct bsd_statfs64* stat)
{
	stat->f_type = lstat->f_type;
	stat->f_bsize = lstat->f_bsize;
	stat->f_blocks = lstat->f_blocks;
	stat->f_bfree = lstat->f_bfree;
	stat->f_bavail = lstat->f_bavail;
	stat->f_files = lstat->f_files;
	stat->f_ffree = lstat->f_ffree;
	stat->f_fsid = lstat->f_fsid;
	stat->f_flags = darling_mount_flags_to_bsd(lstat->f_flags, lstat->f_type);
}
