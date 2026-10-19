#include <sys/errno.h>
#include <darling/emulation/conversion/duct_errno.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/quarantine.h>
#include <darling/emulation/xnu_syscall/bsd/impl/xattr/fsetxattr.h>

#include <sys/errno.h>

#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>

long sys_fsetxattr(int fd, const char* name, const void* value,
		unsigned long size, unsigned int pos, int options)
{
	int ret;
	const char *linux_name;
	char attribute_name[256];
	ret = darwin_xattr_name(name, &linux_name, 1, attribute_name);
	if (ret < 0) return ret;

	if (pos != 0)
		return -ERANGE;

	ret = LINUX_SYSCALL(__NR_fsetxattr, fd, linux_name, value, size, ((options & 2) ? 1 : 0) | ((options & 4) ? 2 : 0));

	if (ret == -LINUX_ENODATA) return -ENOATTR;
	if (ret < 0)
		return errno_linux_to_bsd(ret);

	return ret;
}
