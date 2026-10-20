#ifndef DARLINGSERVER_AUDIT_SESSION_H
#define DARLINGSERVER_AUDIT_SESSION_H
#include <stdint.h>
/* Intel auditinfo_addr_t wire layout. Never serialize host pointers or long. */
typedef struct darling_audit_info {
    uint32_t auid;
    uint32_t mask_success;
    uint32_t mask_failure;
    uint32_t terminal_port;
    uint32_t terminal_type;
    uint32_t terminal_address[4];
    uint32_t asid;
    uint64_t flags;
} darling_audit_info_t;
#endif
