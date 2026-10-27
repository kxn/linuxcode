#include <darling/emulation/xnu_syscall/bsd/impl/process/waitid.h>

#include <stddef.h>

#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/process/wait4.h>
#include <darling/emulation/conversion/signal/duct_signals.h>
#include <darling/emulation/xnu_syscall/bsd/impl/process/wait4.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/xnu_syscall/bsd/helper/bsdthread/cancelable.h>

static void siginfo_linux_to_bsd(const linux_siginfo_t* linux_si, siginfo_t* si);

long sys_waitid(int idtype, int id, siginfo_t* si, int options)
{
	CANCELATION_POINT();
	return sys_waitid_nocancel(idtype, id, si, options);
}

long sys_waitid_nocancel(int idtype, int id, siginfo_t* si, int options)
{
	int ret, linux_options;
	const int allowed = BSD_WNOHANG | BSD_WNOWAIT | BSD_WCONTINUED |
		BSD_WSTOPPED | BSD_WEXITED;
	if (idtype < 0 || idtype > 2 || options == 0 || (options & ~allowed))
		return -EINVAL;

	linux_options = waitopts_bsd_to_linux(options);

	linux_siginfo_t linux_si = {0};
	ret = LINUX_SYSCALL(__NR_waitid, idtype, id, &linux_si, linux_options);
	if (ret < 0)
		return errno_linux_to_bsd(ret);

	// XNU leaves infop untouched when WNOHANG finds no pending child event.
	if (linux_si.linux_si_pid == 0)
		return 0;
	if (si == NULL)
		return -EFAULT;
	siginfo_linux_to_bsd(&linux_si, si);

	return ret;
}

static void siginfo_linux_to_bsd(const linux_siginfo_t* linux_si, siginfo_t* si)
{
	*si = (siginfo_t){0};
	si->si_signo = signum_linux_to_bsd(linux_si->si_signo);
	si->si_errno = errno_linux_to_bsd(linux_si->si_errno);
	si->si_code = linux_si->si_code;
	si->si_pid = linux_si->linux_si_pid;
	si->si_uid = linux_si->linux_si_uid;
	// Child exit status is an exit code only for CLD_EXITED; all other
	// child events carry a signal number in the Linux numbering space.
	si->si_status = linux_si->si_code == CLD_EXITED ?
		linux_si->linux_si_status : signum_linux_to_bsd(linux_si->linux_si_status);
}
