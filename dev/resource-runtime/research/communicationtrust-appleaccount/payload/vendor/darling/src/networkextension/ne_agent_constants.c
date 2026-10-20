/* Fixed NetworkExtension agent identity, matching the original x86_64 ABI. */
#include <uuid/uuid.h>

_Static_assert(sizeof(uuid_t) == 16, "Darwin UUID ABI");
__attribute__((visibility("default"), aligned(16)))
const uuid_t ne_privacy_dns_netagent_id = {
    0x35, 0x3a, 0x4f, 0x9c, 0xce, 0xf5, 0x4c, 0xee,
    0x93, 0xad, 0x46, 0x97, 0xbb, 0x03, 0x18, 0xd7
};
