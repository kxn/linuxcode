#include <sys/errno.h>
#include <darling/emulation/conversion/duct_errno.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/quarantine.h>
#include <darling/emulation/xnu_syscall/bsd/impl/xattr/fremovexattr.h>

#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>

long sys_fremovexattr(int fd, const char* name, int options)
{
	int ret;
	const char *linux_name;
	char attribute_name[256];
	ret = darwin_xattr_name(name, &linux_name, 0, attribute_name);
	if (ret < 0) return ret;

	ret = LINUX_SYSCALL(__NR_fremovexattr, fd, linux_name);

	if (ret == -LINUX_ENODATA) return -ENOATTR;
	if (ret < 0)
		return errno_linux_to_bsd(ret);
	quarantine_removed_fd(fd,linux_name+5);

	return ret;
}
