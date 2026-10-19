#include <darling/emulation/xnu_syscall/bsd/impl/unistd/lseek.h>

#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>

long long sys_lseek(int fd, long long offset, int whence)
{
	long long ret;
	// Darwin sys/_types/_seek_set.h and Linux fs.h assign these operations
	// opposite values. Passing them through can silently copy holes as data
	// and discard the real data during sparse file copies.
	enum { BSD_SEEK_HOLE = 3, BSD_SEEK_DATA = 4,
		LINUX_SEEK_DATA = 3, LINUX_SEEK_HOLE = 4 };
	if (whence == BSD_SEEK_HOLE)
		whence = LINUX_SEEK_HOLE;
	else if (whence == BSD_SEEK_DATA)
		whence = LINUX_SEEK_DATA;

#ifdef SYS__llseek
	long long roff;
	ret = LINUX_SYSCALL(__NR__llseek, fd, (unsigned int)offset >> 32,
			(unsigned int)offset, &roff, whence);

	if (ret >= 0)
		ret = roff;
#else
	ret = LINUX_SYSCALL(__NR_lseek, fd, offset, whence);
#endif
	if (ret < 0)
		ret = errno_linux_to_bsd(ret);

	return ret;
}
