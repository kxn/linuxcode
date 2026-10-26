#ifndef DARLING_SKYWALK_BUILD_COMPAT_H
#define DARLING_SKYWALK_BUILD_COMPAT_H
#ifndef __ASSEMBLER__
#include <stdatomic.h>
#include <stdint.h>
#ifndef __probable
#define __probable(x) __builtin_expect(!!(x), 1)
#endif
#ifndef __improbable
#define __improbable(x) __builtin_expect(!!(x), 0)
#endif
/* Existing libsyscall implementations; avoid implicit call declarations when
 * building with the public SDK and this explicitly staged private header set. */
int _mach_snprintf(char *buffer, int length, const char *format, ...);
int fprintf_stderr(const char *format, ...);
int kdebug_trace(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t);
#endif
#endif
