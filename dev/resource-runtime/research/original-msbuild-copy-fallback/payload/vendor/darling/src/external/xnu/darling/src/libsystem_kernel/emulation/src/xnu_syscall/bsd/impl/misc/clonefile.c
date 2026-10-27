#include <darling/emulation/xnu_syscall/bsd/impl/misc/clonefile.h>

#include <signal.h>

#include <darling/emulation/conversion/duct_errno.h>

long sys_clonefileat(int src_fd, const char* src_path, int dest_fd, const char* dest_path, uint32_t flags) {
	/* The syscall exists, but this backend does not implement file cloning.
	 * Report the unsupported operation so callers can perform a normal copy. */
	return -ENOTSUP;
}

long sys_fclonefileat(int src_fd, int dest_fd, const char* dest_path, uint32_t flags) {
	return -ENOTSUP;
}
