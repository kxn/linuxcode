#ifndef DARLINGSERVER_AUDIT_SESSION_HPP
#define DARLINGSERVER_AUDIT_SESSION_HPP
#include <darlingserver/audit-session.h>
#include <atomic>
#include <cerrno>
#include <memory>
#include <system_error>
namespace DarlingServer {
// A session is owned by server Process objects, surviving Mach-O exec and
// shared with forked children. Session IDs name these actual lifetime objects.
// Audit masks remain per-process, as in XNU credentials.
class AuditSession {
public:
    const darling_audit_info_t info;
    static std::shared_ptr<const AuditSession> create(darling_audit_info_t info) {
        static std::atomic<uint64_t> next{1};
        uint64_t id=next.fetch_add(1,std::memory_order_relaxed);
        if (id>=UINT32_MAX) throw std::system_error(EOVERFLOW,std::generic_category());
        info.asid=(uint32_t)id;
        info.mask_success=info.mask_failure=0;
        return std::shared_ptr<const AuditSession>(new AuditSession(info));
    }
private:
    explicit AuditSession(darling_audit_info_t value):info(value) {}
};
static_assert(sizeof(darling_audit_info_t)==48,"Intel auditinfo_addr_t layout");
}
#endif
