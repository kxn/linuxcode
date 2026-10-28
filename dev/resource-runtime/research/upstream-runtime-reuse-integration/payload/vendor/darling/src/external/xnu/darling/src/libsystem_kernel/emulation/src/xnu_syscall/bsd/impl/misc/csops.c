#include <darling/emulation/xnu_syscall/bsd/impl/misc/csops.h>
#include <darling/emulation/conversion/errno.h>
#include <darlingserver/rpc.h>
#include <stdint.h>

/* The server validates the actual loaded executable and audit generation,
 * verifies its descriptor-backed code signature and safely copies its metadata.
 * No AMFI/platform identity or entitlement enforcement is synthesized here. */
long sys_csops_audittoken(int pid, unsigned int ops, void* useraddr, size_t usersize, audit_token_t* token) {
    int ret = dserver_rpc_csops(pid, ops, (uint64_t)(uintptr_t)useraddr,
        usersize, (uint64_t)(uintptr_t)token);
    return ret < 0 ? errno_linux_to_bsd(ret) : ret;
}

long sys_csops(int pid, unsigned int ops, void* useraddr, size_t usersize) {
    return sys_csops_audittoken(pid, ops, useraddr, usersize, 0);
}
