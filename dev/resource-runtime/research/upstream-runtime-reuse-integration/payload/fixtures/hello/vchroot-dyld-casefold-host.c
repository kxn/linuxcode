/* Reuse the actual-source harness; locale access during bootstrap is fatal. */
#define VARIANT_DYLD
#define strcasecmp vchroot_bootstrap_forbidden_locale_compare
#include "vchroot-unicode-host.c"
int vchroot_bootstrap_forbidden_locale_compare(const char* left, const char* right)
{
    (void)left; (void)right;
    __builtin_trap();
}
