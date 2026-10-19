#include <sys/errno.h>
#include <darling/emulation/conversion/duct_errno.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/quarantine.h>
#include <darling/emulation/xnu_syscall/bsd/impl/xattr/setxattr.h>

#include <sys/errno.h>

#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>

#include <darling/emulation/linux_premigration/vchroot_expand.h>
#include <darling/emulation/common/bsdthread/per_thread_wd.h>
#include <string.h>

#define XATTR_NOFOLLOW	1

long sys_setxattr(const char* path, const char* name, const void* value,
		unsigned long size, unsigned int pos, int options)
{
	int ret;
	const char *linux_name;
	char attribute_name[256];
	ret = darwin_xattr_name(name, &linux_name, 1, attribute_name);
	if (ret < 0) return ret;

	if (pos != 0)
		return -ERANGE;

	struct vchroot_expand_args vc;
	vc.flags=(options & XATTR_NOFOLLOW)?0:VCHROOT_FOLLOW;vc.dfd=get_perthread_wd();strcpy(vc.path,path);
	ret=vchroot_expand(&vc);if(ret<0)return errno_linux_to_bsd(ret);

	if (options & XATTR_NOFOLLOW)
	{
		ret = LINUX_SYSCALL(__NR_lsetxattr, vc.path, linux_name, value, size, ((options & 2) ? 1 : 0) | ((options & 4) ? 2 : 0));
	}
	else
	{
		ret = LINUX_SYSCALL(__NR_setxattr, vc.path, linux_name, value, size, ((options & 2) ? 1 : 0) | ((options & 4) ? 2 : 0));
	}

	if (ret == -LINUX_ENODATA) return -ENOATTR;
	if (ret < 0)
		return errno_linux_to_bsd(ret);

	return ret;
}
