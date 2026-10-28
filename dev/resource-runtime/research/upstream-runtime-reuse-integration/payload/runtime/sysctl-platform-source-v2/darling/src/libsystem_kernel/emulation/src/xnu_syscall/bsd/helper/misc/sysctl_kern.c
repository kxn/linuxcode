#include <darling-config.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/sysctl_kern.h>

#include <sys/errno.h>
#include <limits.h>

#include <darling/emulation/xnu_syscall/bsd/helper/misc/sysctl_proc.h>
#include <darling/emulation/xnu_syscall/bsd/impl/misc/getrlimit.h>
#include <darling/emulation/linux_premigration/ext/sysinfo.h>
#include <darling/emulation/linux_premigration/ext/syslog.h>
#include <darling/emulation/linux_premigration/ext/sys/utsname.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/xnu_syscall/bsd/impl/time/gettimeofday.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/fcntl/open.h>
#include <darling/emulation/common/simple.h>
#include <darling/emulation/xnu_syscall/bsd/impl/fcntl/open.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/read.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/close.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/readline.h>
#include <darling/emulation/linux_premigration/elfcalls_wrapper.h>

#include <darling-config.h>

enum {
	_KERN_MSGBUF = 1000,
	_KERN_OSPRODUCTVERSION,
	_KERN_MEMORYSTATUS_LEVEL,

	_KERN_SEMMNS = 1000,
};

static sysctl_handler(handle_msgbuf);
static sysctl_handler(handle_proc);
static sysctl_handler(handle_procargs32);
static sysctl_handler(handle_argmax);
static sysctl_handler(handle_boottime);
static sysctl_handler(handle_ostype);
static sysctl_handler(handle_hostname);
static sysctl_handler(handle_domainname);
static sysctl_handler(handle_osrelease);
static sysctl_handler(handle_version);
static sysctl_handler(handle_osversion);
static sysctl_handler(handle_maxproc);
static sysctl_handler(handle_netboot);
static sysctl_handler(handle_safeboot);
static sysctl_handler(handle_usrstack32);
static sysctl_handler(handle_usrstack64);
static sysctl_handler(handle_sysv_semmns);
static sysctl_handler(handle_osproductversion);
static sysctl_handler(handle_osrevision);
static sysctl_handler(handle_memorystatus_level);

extern int _sysctl_proc(int what, int flag, struct kinfo_proc* out, unsigned long* buflen);
extern int _sysctl_procargs(int pid, char* buf, unsigned long* buflen);
extern int strlcpy(char* dst, const char* src, __SIZE_TYPE__ dst_size);
extern __SIZE_TYPE__ strlen(const char* str);
extern int strncmp(const char* a, const char* b, __SIZE_TYPE__ length);

const struct known_sysctl sysctls_kern_sysv[] = {
	{ .oid = _KERN_SEMMNS, .type = CTLTYPE_INT, .exttype = "I", .name = "semmns", .handler = handle_sysv_semmns },
	{ .oid = -1 }
};

const struct known_sysctl sysctls_kern[] = {
	{ .oid = _KERN_MSGBUF, .type = CTLTYPE_STRING, .exttype = "S", .name = "msgbuf", .handler = handle_msgbuf },
	{ .oid = KERN_PROC, .type = CTLTYPE_STRUCT, .exttype = "", .name = "proc", .handler = handle_proc },
	{ .oid = KERN_PROCARGS2, .type = CTLTYPE_STRUCT, .exttype = "", .name = "procargs2", .handler = handle_procargs32 },
	{ .oid = KERN_ARGMAX, .type = CTLTYPE_INT, .exttype = "I", .name = "argmax", .handler = handle_argmax },
	{ .oid = KERN_MAXPROC, .type = CTLTYPE_INT, .exttype = "I", .name = "maxproc", .handler = handle_maxproc },
	{ .oid = KERN_NETBOOT, .type = CTLTYPE_INT, .exttype = "I", .name = "netboot", .handler = handle_netboot },
	{ .oid = KERN_SAFEBOOT, .type = CTLTYPE_INT, .exttype = "I", .name = "safeboot", .handler = handle_safeboot },
	{ .oid = KERN_BOOTTIME, .type = CTLTYPE_STRUCT, .exttype = "S,timeval", .name = "boottime", .handler = handle_boottime },
	{ .oid = KERN_OSTYPE, .type = CTLTYPE_STRING, .exttype = "S", .name = "ostype", .handler = handle_ostype },
	{ .oid = KERN_HOSTNAME, .type = CTLTYPE_STRING, .exttype = "S", .name = "hostname", .handler = handle_hostname },
	{ .oid = KERN_DOMAINNAME, .type = CTLTYPE_STRING, .exttype = "S", .name = "domainname", .handler = handle_domainname },
	{ .oid = KERN_OSRELEASE, .type = CTLTYPE_STRING, .exttype = "S", .name = "osrelease", .handler = handle_osrelease },
	{ .oid = KERN_VERSION, .type = CTLTYPE_STRING, .exttype = "S", .name = "version", .handler = handle_version },
	{ .oid = KERN_OSVERSION, .type = CTLTYPE_STRING, .exttype = "S", .name = "osversion", .handler = handle_osversion },
	{ .oid = KERN_USRSTACK32, .type = CTLTYPE_INT, .exttype = "I", .name = "usrstack", .handler = handle_usrstack32 },
	{ .oid = KERN_USRSTACK64, .type = CTLTYPE_QUAD, .exttype = "Q", .name = "usrstack64", .handler = handle_usrstack64 },
	{ .oid = _KERN_OSPRODUCTVERSION, .type = CTLTYPE_STRING, .exttype = "S", .name = "osproductversion", .handler = handle_osproductversion },
	{ .oid = KERN_OSREV, .type = CTLTYPE_INT, .exttype = "I", .name = "osrevision", .handler = handle_osrevision },
	{ .oid = KERN_SYSV, .type = CTLTYPE_NODE, .exttype = "", .name = "sysv", .subctls = sysctls_kern_sysv },
	{ .oid = _KERN_MEMORYSTATUS_LEVEL, .type = CTLTYPE_INT, .exttype = "IU", .name = "memorystatus_level", .handler = handle_memorystatus_level },
	{ .oid = -1 }
};

sysctl_handler(handle_msgbuf)
{
	if (*oldlen <= 8)
	{
		// Caller is asking for buffer size
		if (*oldlen < sizeof(int))
			return -EINVAL;

		*((int*) old) = __linux_syslog(SYSLOG_ACTION_SIZE_BUFFER, NULL, 0);
	}
	else
	{
		// Caller is asking for buffer contents
		int ret;

		ret = __linux_syslog(SYSLOG_ACTION_READ_ALL, (char*) old, *oldlen);
		if (ret < 0)
			return errno_linux_to_bsd(ret);

		*oldlen = ret;
	}
	return 0;
}

sysctl_handler(handle_proc)
{
	if (nlen < 4)
		return -ENOENT;
	return _sysctl_proc(name[2], name[3], (struct kinfo_proc*) old, oldlen);
}

sysctl_handler(handle_procargs32)
{
	if (nlen < 3)
		return -ENOENT;
	return _sysctl_procargs(name[2], (char*) old, oldlen);
}

sysctl_handler(handle_argmax)
{
	struct xnu_rlimit lim;
	int r;
	int* ovalue = (int*) old;

	r = sys_getrlimit(BSD_RLIMIT_STACK, &lim);
	if (r < 0)
		return r;

	if (ovalue != NULL)
		*ovalue = lim.rlim_cur / 4;
	*oldlen = sizeof(int);
	return 0;
}

sysctl_handler(handle_boottime)
{
	struct bsd_timeval* tv = (struct bsd_timeval*)old;
	if (!oldlen)
		return -EINVAL;
	if (!tv) {
		*oldlen = sizeof(*tv);
		return 0;
	}
	if (*oldlen < sizeof(*tv))
		return -EINVAL;

	// Rounded sysinfo uptime subtracted from a fresh wall clock makes the
	// reported epoch jump by a second. libc's CLOCK_MONOTONIC fallback then
	// moves backwards. Use the same actual Linux boot epoch as proc_pidinfo.
	// Linux exposes btime at second precision; retain that stable value.
	int fd = sys_open(DARLING_PROCFS_PATH "/stat", BSD_O_RDONLY, 0);
	if (fd < 0)
		return fd;
	struct rdline_buffer buffer;
	_readline_init(&buffer);
	const char* line;
	unsigned long long boot = 0;
	while ((line = _readline(fd, &buffer)) != NULL) {
		if (strncmp(line, "btime ", 6) == 0) {
			const char* end;
			boot = __simple_atoi(line + 6, &end);
			if (end == line + 6 || *end != '\0')
				boot = 0;
			break;
		}
	}
	close_internal(fd);
	if (!boot)
		return -EIO;
	tv->tv_sec = boot;
	tv->tv_usec = 0;
	*oldlen = sizeof(*tv);
	return 0;
}

sysctl_handler(handle_ostype)
{
	const char* s = EMULATED_SYSNAME;

	return copyout_readonly_string(s, (char*) old, oldlen, _new, newlen);
}

sysctl_handler(handle_osrelease)
{
	const char* s = EMULATED_RELEASE;

	return copyout_readonly_string(s, (char*) old, oldlen, _new, newlen);
}

sysctl_handler(handle_version)
{
	const char* s = EMULATED_VERSION;

	return copyout_readonly_string(s, (char*) old, oldlen, _new, newlen);
}

sysctl_handler(handle_osversion)
{
	const char* s = EMULATED_OSVERSION;

	return copyout_readonly_string(s, (char*) old, oldlen, _new, newlen);
}


static struct linux_utsname lu;
struct linux_utsname* need_uname(void)
{
#ifndef VARIANT_DYLD
	// Cache __linux_uname results
	if (!lu.sysname[0])
	{
		__linux_uname(&lu);
	}
#endif
	return &lu;
}

sysctl_handler(handle_hostname)
{
	int rv = 0;
	
	need_uname();
	rv = copyout_string(lu.nodename, (char*) old, oldlen);
	if (rv) return rv;
	
	if (_new && newlen > 0)
	{
		rv = LINUX_SYSCALL(__NR_sethostname, _new, newlen);
		if (rv < 0)
			rv = errno_linux_to_bsd(rv);
	}
	
	return rv;
}

sysctl_handler(handle_domainname)
{
	int rv = 0;
	
	need_uname();
	rv = copyout_string(lu.domainname, (char*) old, oldlen);
	if (rv) return rv;
	
	if (_new && newlen > 0)
	{
		rv = LINUX_SYSCALL(__NR_setdomainname, _new, newlen);
		if (rv < 0)
			rv = errno_linux_to_bsd(rv);
	}
	
	return rv;
}

sysctl_handler(handle_maxproc)
{
	char buf[16];
	int fd = sys_open(DARLING_PROCFS_PATH "/sys/kernel/pid_max", BSD_O_RDONLY, 0);
	int value = 1024;
	int* ovalue = (int*) old;
	
	if (!oldlen)
		return -EINVAL;
	
	if (fd >= 0)
	{
		int rd = sys_read(fd, buf, sizeof(buf) - 1);
		close_internal(fd);
		
		if (rd > 0)
		{
			buf[rd] = '\0';
			value = __simple_atoi(buf, NULL);
		}
	}
	
	if (ovalue != NULL)
		*ovalue = value;
	*oldlen = sizeof(int);
	
	return 0;
}

sysctl_handler(handle_netboot)
{
	int* ovalue = (int*) old;
	if (!oldlen)
		return -EINVAL;

	if (*oldlen >= sizeof(int))
		*ovalue = 0;
	*oldlen = sizeof(int);

	return 0;
}

sysctl_handler(handle_safeboot)
{
	int* ovalue = (int*) old;
	if (!oldlen)
		return -EINVAL;

	if (*oldlen >= sizeof(int))
		*ovalue = 0;
	*oldlen = sizeof(int);

	return 0;
}

sysctl_handler(handle_sysv_semmns)
{
	int* ovalue = (int*) old;
	if (!oldlen)
		return -EINVAL;
	if (*oldlen >= sizeof(int))
		*ovalue = -1;
	*oldlen = sizeof(int);
	return 0;
}

sysctl_handler(handle_usrstack32)
{
	unsigned int* ovalue = (unsigned int*) old;
	if (ovalue)
		*ovalue = __darling_thread_get_stack();
	*oldlen = sizeof(*ovalue);
	return 0;
}

sysctl_handler(handle_usrstack64)
{
	unsigned long long* ovalue = (unsigned long long*) old;
	if (ovalue)
		*ovalue = __darling_thread_get_stack();
	*oldlen = sizeof(*ovalue);
	return 0;
}

static sysctl_handler(handle_osproductversion) {
	return copyout_readonly_string(EMULATED_OSPRODUCTVERSION, (char*)old, oldlen, _new, newlen);
};

// Apple no longer changes this value
// https://lists.apple.com/archives/darwin-dev/2005/Jul/msg00029.html
#define EMULATED_OSREVISION 199506

static sysctl_handler(handle_osrevision) {
	int* ovalue = (int*)old;
	if (ovalue)
		*ovalue = EMULATED_OSREVISION;
	*oldlen = sizeof(*ovalue);
	return 0;
}

/* Darwin exposes available pages as a percentage of physical pages here.
 * Linux MemAvailable includes reclaimable memory; use it as the host's
 * availability estimate rather than claiming to implement Darwin jetsam. */
static int meminfo_kib(const char* text, unsigned long long* result)
{
    while (*text == ' ' || *text == '\t') ++text;
    if (*text < '0' || *text > '9') return -EIO;
    unsigned long long value = 0;
    do {
        unsigned digit = *text++ - '0';
        if (value > (ULLONG_MAX - digit) / 10) return -EIO;
        value = value * 10 + digit;
    } while (*text >= '0' && *text <= '9');
    while (*text == ' ' || *text == '\t') ++text;
    if (text[0] != 'k' || text[1] != 'B' || text[2] != '\0') return -EIO;
    *result = value;
    return 0;
}

sysctl_handler(handle_memorystatus_level)
{
    if (_new || newlen) return -EPERM;
    if (!oldlen) return -EFAULT;
    unsigned long capacity = *oldlen;
    *oldlen = sizeof(unsigned);
    if (!old) return 0;
    if (capacity < sizeof(unsigned)) {
        /* sysctl_old_user rejects a short integer before advancing oldidx. */
        *oldlen = 0;
        return -ENOMEM;
    }
    int fd = sys_open(DARLING_PROCFS_PATH "/meminfo", BSD_O_RDONLY, 0);
    if (fd < 0) return fd;
    struct rdline_buffer buffer;
    _readline_init(&buffer);
    const char* line;
    unsigned long long total = 0, available = 0;
    unsigned seen = 0;
    int status = 0;
    while ((line = _readline(fd, &buffer)) != NULL) {
        if (!strncmp(line, "MemTotal:", 9)) {
            status = meminfo_kib(line + 9, &total); seen |= 1;
        } else if (!strncmp(line, "MemAvailable:", 13)) {
            status = meminfo_kib(line + 13, &available); seen |= 2;
        }
        if (status || seen == 3) break;
    }
    close_internal(fd);
    if (status) return status;
    if (seen != 3 || !total || total > ULLONG_MAX / 100) return -EIO;
    if (available > total) available = total;
    *(unsigned*)old = (unsigned)(available * 100 / total);
    return 0;
}
