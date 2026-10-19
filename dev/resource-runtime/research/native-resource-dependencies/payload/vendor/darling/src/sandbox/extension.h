#ifndef DARLING_SANDBOX_EXTENSION_H
#define DARLING_SANDBOX_EXTENSION_H
#include <stdint.h>
#include <sys/types.h>
#include <mach/message.h>
#ifdef __cplusplus
extern "C" {
#endif
extern const char* const APP_SANDBOX_IOKIT_CLIENT;
extern const char* const APP_SANDBOX_MACH;
extern const char* const APP_SANDBOX_READ;
extern const char* const APP_SANDBOX_READ_WRITE;
extern const uint32_t SANDBOX_EXTENSION_CANONICAL;
extern const uint32_t SANDBOX_EXTENSION_DEFAULT;
extern const uint32_t SANDBOX_EXTENSION_NO_REPORT;
extern const uint32_t SANDBOX_EXTENSION_PREFIXMATCH;
extern const uint32_t SANDBOX_EXTENSION_NOFOLLOW;
extern const uint32_t SANDBOX_EXTENSION_NOFOLLOW_ANY;
extern const uint32_t SANDBOX_EXTENSION_NO_STORAGE_CLASS;
extern const uint32_t SANDBOX_EXTENSION_USER_INTENT;
extern const uint32_t SANDBOX_EXTENSION_MACL_LEARNING;
char* sandbox_extension_issue_file(const char* extension_class, const char* path, uint32_t flags);
char* sandbox_extension_issue_file_to_process(const char* extension_class, const char* path, uint32_t flags, audit_token_t token);
char* sandbox_extension_issue_file_to_process_by_pid(const char* extension_class, const char* path, uint32_t flags, pid_t pid);
char* sandbox_extension_issue_file_to_self(const char* extension_class, const char* path, uint32_t flags);
int64_t sandbox_extension_consume(const char* token);
int sandbox_extension_release(int64_t handle);
#ifdef __cplusplus
}
#endif
#endif
