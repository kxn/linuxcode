#include <darling/emulation/xnu_syscall/bsd/impl/stat/mkfifoat.h>

#include <sys/errno.h>

#include <darling/emulation/conversion/stat/common.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/conversion/common_at.h>
#include <darling/emulation/linux_premigration/vchroot_expand.h>
#include <darling/emulation/other/mach/lkm.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/sandbox_fs.h>

#define LINUX_S_IFIFO 0010000

static long create_nodeat(int fd, const char* path, unsigned int mode, unsigned long device)
{
	int ret;
	struct vchroot_expand_args vc;

	if (!path)
		return -EFAULT;

	vc.flags = 0;
	vc.dfd = atfd(fd);
	
	ret = sandbox_fs_copy_path(vc.path, sizeof vc.path, path);
	if (ret < 0) return ret;
	if (!vc.path[0]) return -ENOENT;
	if (vc.path[0] != '/' && vc.dfd != LINUX_AT_FDCWD) {
		struct linux_stat info;
		ret = LINUX_SYSCALL(__NR_fstat, vc.dfd, &info);
		if (ret < 0) return errno_linux_to_bsd(ret);
		if ((info.st_mode & 0170000) != 0040000) return -ENOTDIR;
	}

	ret = vchroot_expand(&vc);
	if (ret < 0)
		return errno_linux_to_bsd(ret);

	struct sandbox_fs_path target;
	ret = sandbox_fs_prepare(&vc, &target);
	if (ret < 0) return ret;
	ret = sandbox_fs_authorize("file-write-create", &target);
	if (!ret) {
		ret = LINUX_SYSCALL(__NR_mknodat, target.directory, target.leaf, mode, device);
		if (ret < 0) ret = errno_linux_to_bsd(ret);
	}
	sandbox_fs_close(&target);
	return ret;
}

long sys_mkfifoat(int fd, const char* path, unsigned int mode)
{
	return create_nodeat(fd, path, (mode & 07777) | LINUX_S_IFIFO, 0);
}

long sys_mknodat(int fd, const char* path, unsigned int mode, unsigned int device)
{
	unsigned int type = mode & 0170000;
	if (type != LINUX_S_IFIFO && type != 0020000 && type != 0060000)
		return -EINVAL;
	// Darwin dev_t stores an 8-bit major and a 24-bit minor.
	unsigned long major = device >> 24, minor = device & 0xffffff;
	unsigned long linux_device = (minor & 0xff) | (major << 8) | ((minor & ~0xfful) << 12);
	return create_nodeat(fd, path, type | (mode & 07777), linux_device);
}
