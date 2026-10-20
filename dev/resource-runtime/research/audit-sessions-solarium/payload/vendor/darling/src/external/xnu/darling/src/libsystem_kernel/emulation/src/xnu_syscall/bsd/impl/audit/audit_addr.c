#include <darling/emulation/xnu_syscall/bsd/impl/audit/audit_addr.h>
#include <darling/emulation/conversion/errno.h>
#include <darlingserver/rpc.h>
#include <darlingserver/audit-session.h>
#include <stddef.h>

_Static_assert(sizeof(auditinfo_addr_t)==sizeof(darling_audit_info_t), "Intel audit wire size");
_Static_assert(offsetof(auditinfo_addr_t,ai_asid)==offsetof(darling_audit_info_t,asid), "audit ID offset");
_Static_assert(offsetof(auditinfo_addr_t,ai_flags)==offsetof(darling_audit_info_t,flags), "audit flags offset");

// Server-owned process state survives exec and is inherited at actual fork.
// Copying is performed by the server's checked process-memory interface,
// preserving partial-length copy semantics without dereferencing guest pointers.
long sys_getaudit_addr(struct auditinfo_addr* info, int length) {
    int result=dserver_rpc_audit_info(0,info,(uint32_t)length);
    return result<0 ? errno_linux_to_bsd(result) : result;
}

long sys_setaudit_addr(struct auditinfo_addr* info, int length) {
    int result=dserver_rpc_audit_info(1,info,(uint32_t)length);
    return result<0 ? errno_linux_to_bsd(result) : result;
}
