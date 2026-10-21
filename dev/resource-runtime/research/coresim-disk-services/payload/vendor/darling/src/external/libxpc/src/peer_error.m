/* This file is part of Darling, distributed under GPL-3.0-or-later. */
#import <xpc/objects/error.h>
#import <xpc/objects/string.h>
#import <xpc/xpc.h>
#import <xpc/util.h>

/* Keep the singleton in the existing backend image. A libSystem reexport to
 * a separate Objective-C adapter creates an initialization dependency cycle.
 * This object describes an error; it does not implement peer verification.
 */
struct _xpc_dictionary_s {
    struct xpc_error_s the_real_thing;
};
static struct xpc_string_s peer_description = {
    .base = { XPC_GLOBAL_OBJECT_HEADER(string) },
    .byteLength = NSUIntegerMax,
    .string = "Peer Forbidden",
    .freeWhenDone = false,
};
extern const struct _xpc_dictionary_s _xpc_error_peer_code_signing_requirement;
static struct xpc_dictionary_entry_s peer_description_entry = {
    .link = {
        .le_next = NULL,
        .le_prev = (struct xpc_dictionary_entry_s **)&LIST_FIRST(
            &_xpc_error_peer_code_signing_requirement.the_real_thing.base.head),
    },
    .object = XPC_CAST(string, &peer_description),
    .name = "XPCErrorDescription",
};
XPC_EXPORT const struct _xpc_dictionary_s _xpc_error_peer_code_signing_requirement = {
    .the_real_thing = {
        .base = {
            .base = { XPC_GLOBAL_OBJECT_HEADER(error) },
            .size = 1,
            .head = { .lh_first = &peer_description_entry },
        },
    },
};
