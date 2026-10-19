/* Data object ABI from the pinned Intel libsystem_sandbox image.
 * Exporting a flag does not add the corresponding kernel policy operation.
 */
#include <stdint.h>

const uint32_t SANDBOX_EXTENSION_NOFOLLOW = 32;
const uint32_t SANDBOX_EXTENSION_NOFOLLOW_ANY = 2;
const uint32_t SANDBOX_EXTENSION_NO_STORAGE_CLASS = 64;
const uint32_t SANDBOX_EXTENSION_USER_INTENT = 16384;
const uint32_t SANDBOX_EXTENSION_MACL_LEARNING = 32768;
