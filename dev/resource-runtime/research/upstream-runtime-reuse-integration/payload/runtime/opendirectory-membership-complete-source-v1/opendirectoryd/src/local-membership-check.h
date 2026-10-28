/* Local NSS membership checks; successful identifier translation is not a grant. */
#ifndef ODD_LOCAL_MEMBERSHIP_CHECK_H
#define ODD_LOCAL_MEMBERSHIP_CHECK_H
#include <stdbool.h>
#include <stddef.h>
/* Return zero or a positive errno. The output is always zero on error.
 * No cache is maintained: refresh and ordinary checks both read current NSS.
 * Only local passwd/group identities are supported. Network/SID forms return
 * ENOTSUP. NSS is responsible for any nested membership it can represent. */
int linuxcode_check_membership(int user_type, const void *user, size_t user_size,
    int group_type, const void *group, size_t group_size, bool refresh, int *is_member);
/* Apple SACL order: all_services if it exists, otherwise the specific group;
 * neither defined -> ENOENT, never an implicit successful membership result. */
int linuxcode_check_service_membership(int user_type, const void *user,
    size_t user_size, const char *service, int *is_member);
#endif
