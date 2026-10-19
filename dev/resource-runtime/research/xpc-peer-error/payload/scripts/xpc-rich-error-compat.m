// Uses Darling's real OS_xpc_object allocation/retention ABI. Native rich-error
// object storage is private and is deliberately not copied into that ABI.
#import <Foundation/Foundation.h>
#include <xpc/xpc.h>
#include <objc/runtime.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <mach-o/loader.h>
#include <dlfcn.h>
#include <stdio.h>
#include <pthread.h>
#include "connection-backend.h"

@interface OS_xpc_object : NSObject
+ (NSUInteger)instanceSize;
@end
@interface OS_xpc_rich_error : OS_xpc_object
- (instancetype)initWithText:(const char *)text retry:(bool)retry;
- (char *)xpcDescription;
@end

struct ObjectHeader { const void *isa; int32_t refs,xrefs; };
struct RichError { struct ObjectHeader base; bool retry; char *text; };
_Static_assert(sizeof(struct ObjectHeader)==16,"Darling XPC base ABI");
_Static_assert(sizeof(struct RichError)==32,"Rich error adapter storage");
__asm__(".globl __xpc_type_rich_error\n.equiv __xpc_type_rich_error, _OBJC_CLASS_$_OS_xpc_rich_error");

@implementation OS_xpc_rich_error
+ (void)load {
    if ([OS_xpc_object instanceSize]!=sizeof(struct ObjectHeader)) __builtin_trap();
}
+ (NSUInteger)instanceSize { return sizeof(struct RichError); }
- (instancetype)initWithText:(const char *)text retry:(bool)retry {
    self=[super init];
    if (self) {
        struct RichError *value=(void *)self;
        value->text=strdup(text);value->retry=retry;
        if (!value->text) { [self release];return nil; }
    }
    return self;
}
- (char *)xpcDescription { return strdup(((struct RichError *)(void *)self)->text); }
- (void)dealloc { free(((struct RichError *)(void *)self)->text);[super dealloc]; }
@end

// Explicit adapter factory for actual failure paths/tests. No unsupported
// Apple private constructor signature or modern session implementation is
// claimed by this symbol.
xpc_object_t darling_xpc_rich_error_create(const char *text,bool retry) {
    if (!text) { errno=EINVAL;return NULL; }
    return (xpc_object_t)[[OS_xpc_rich_error alloc] initWithText:text retry:retry];
}
static struct RichError *checked(xpc_rich_error_t error) {
    if (!error || object_getClass((id)error)!=[OS_xpc_rich_error class]) __builtin_trap();
    return (struct RichError *)(void *)error;
}
char *xpc_rich_error_copy_description(xpc_rich_error_t error) {
    return strdup(checked(error)->text);
}
bool xpc_rich_error_can_retry(xpc_rich_error_t error) { return checked(error)->retry; }

// Same real immutable global-dictionary representation as Darling error.m.
// The description "Peer Forbidden" is read from the pinned native singleton.
#ifndef LINUXCODE_XPC_PEER_ERROR_FROM_BACKEND
struct StringObject { struct ObjectHeader base; uintptr_t byteLength; BOOL freeWhenDone; const char *string; };
struct Entry { struct Entry *next,**previous; const void *object; char name[20]; };
struct Dictionary { struct ObjectHeader base; uintptr_t count; struct Entry *head;
    void *connection; uint32_t incoming,outgoing; uint32_t audit[8]; };
struct _xpc_dictionary_s { struct Dictionary value; };
_Static_assert(sizeof(struct Dictionary)==80,"Pinned Darling dictionary ABI");
_Static_assert(sizeof(struct StringObject)==40,"Pinned Darling string ABI");
extern const struct _xpc_dictionary_s _xpc_error_peer_code_signing_requirement;
static const struct StringObject peerText={
    {&_xpc_type_string,INT32_MAX,INT32_MAX},UINTPTR_MAX,NO,"Peer Forbidden"};
static struct Entry peerEntry={NULL,
    (struct Entry **)(void *)&_xpc_error_peer_code_signing_requirement.value.head,
    &peerText,"XPCErrorDescription"};
const struct _xpc_dictionary_s _xpc_error_peer_code_signing_requirement={
    .value={.base={&_xpc_type_error,INT32_MAX,INT32_MAX},.count=1,.head=&peerEntry}};
#endif

static void connection_incompatible(void) {
    fputs("XPC connection backend UUID/code/layout guard rejected incompatible runtime\n",stderr);
    __builtin_trap();
}
static pthread_once_t connection_api_once=PTHREAD_ONCE_INIT;
static char *(*backend_copy_reason)(xpc_connection_t);
static int (*backend_set_requirement)(xpc_connection_t,const char *);
static void resolve_connection_api(void) {
    void *library=dlopen("/usr/lib/system/libxpc.dylib",RTLD_LAZY|RTLD_LOCAL);
    if (!library)return;
    Dl_info backend,owner;
    if (!dladdr((void *)xpc_connection_cancel,&backend))return;
    void *reason=dlsym(library,"xpc_connection_copy_invalidation_reason");
    void *requirement=dlsym(library,"xpc_connection_set_peer_code_signing_requirement");
    // Only call a function owned by the exact library that implements the
    // connection API. Never recurse into this adapter via a reexport cycle.
    if (reason && reason!=(void *)xpc_connection_copy_invalidation_reason &&
        dladdr(reason,&owner) && owner.dli_fbase==backend.dli_fbase)
        backend_copy_reason=reason;
    if (requirement && requirement!=(void *)xpc_connection_set_peer_code_signing_requirement &&
        dladdr(requirement,&owner) && owner.dli_fbase==backend.dli_fbase)
        backend_set_requirement=requirement;
}
static void check_connection(xpc_connection_t connection) {
    if (!connection || xpc_get_type((xpc_object_t)connection)!=XPC_TYPE_CONNECTION)connection_incompatible();
    if ([(id)connection.class instanceSize]!=connection_backend_size)connection_incompatible();
    Dl_info info;
    if (!dladdr((void *)xpc_connection_cancel,&info))connection_incompatible();
    const struct mach_header_64 *header=info.dli_fbase;
    if (header->magic!=MH_MAGIC_64 || header->ncmds>4096)connection_incompatible();
    const unsigned char *cursor=(void *)(header+1),*end=cursor+header->sizeofcmds;
    bool found=false;
    for(uint32_t i=0;i<header->ncmds;i++) {
        const struct load_command *cmd=(void *)cursor;
        if(cursor+8>end || cmd->cmdsize<8 || cursor+cmd->cmdsize>end)connection_incompatible();
        if(cmd->cmd==LC_UUID) {
            if(cmd->cmdsize!=24 || memcmp(cursor+8,connection_backend_uuid,16))connection_incompatible();
            found=true;
        }
        cursor+=cmd->cmdsize;
    }
    if(!found || memcmp((char *)info.dli_fbase+connection_cancel_event_offset,
        connection_cancel_event_bytes,sizeof(connection_cancel_event_bytes)))connection_incompatible();
}
char *xpc_connection_copy_invalidation_reason(xpc_connection_t connection) {
    pthread_once(&connection_api_once,resolve_connection_api);
    if (backend_copy_reason)return backend_copy_reason(connection);
    check_connection(connection);
    // Pinned backend has one terminal state, set immediately before delivering
    // XPC_ERROR_CONNECTION_INVALID. Never invent a code-signing failure cause.
    const volatile bool *cancelled=(void *)((char *)connection+connection_cancelled_offset);
    return *cancelled ? strdup("Connection cancelled by the Darling XPC backend") : NULL;
}
int xpc_connection_set_peer_code_signing_requirement(xpc_connection_t connection,const char *requirement) {
    pthread_once(&connection_api_once,resolve_connection_api);
    if (backend_set_requirement)return backend_set_requirement(connection,requirement);
    check_connection(connection);
    // This backend has no per-message code-signing enforcement. Returning an
    // error follows the SDK unsupported-platform contract; never report that
    // an uninstalled requirement was accepted.
    return ENOTSUP;
}
