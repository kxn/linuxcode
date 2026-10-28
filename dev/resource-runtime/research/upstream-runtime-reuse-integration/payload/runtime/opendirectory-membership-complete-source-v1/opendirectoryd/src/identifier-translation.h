/* Local identifier translation; identity conversion does not prove membership. */
#ifndef ODD_IDENTIFIER_TRANSLATION_H
#define ODD_IDENTIFIER_TRANSLATION_H
#include <membership.h>
#include <membershipPriv.h>
#include <stddef.h>
#include <sys/types.h>
#include <uuid/uuid.h>

/* Return zero or an errno value. `record_type` is MBR_REC_TYPE_USER/GROUP.
 * Compatibility UUID decoding does not test whether the record exists. */
int od_compat_uuid_decode(const uuid_t uuid, id_t *identifier, int *record_type);

/* On success *result is malloc-owned; *result_size is its exact wire size.
 * Names include their terminating NUL, UUIDs have 16 bytes, IDs sizeof(id_t).
 * All outputs remain unchanged on error. Local records have no GeneratedUID
 * attribute, so numeric and named records share Apple's compatibility format. */
int od_identifier_resolve(int type, const void *identifier, size_t size,
                        int target_type, void **result, size_t *result_size,
                        int *record_type);
#endif
