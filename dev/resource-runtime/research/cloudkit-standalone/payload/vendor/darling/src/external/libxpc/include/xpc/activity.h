/**
 * This file is part of Darling.
 *
 * Copyright (C) 2023 Darling developers
 *
 * Darling is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * Darling is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Darling.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifndef __XPC_ACTIVITY_H__
#define __XPC_ACTIVITY_H__

#ifndef __XPC_INDIRECT__
#error "It's not recommended to directly include <xpc/activity.h>, please #include <xpc/xpc.h> instead."
#endif

#include <xpc/base.h>

#ifdef __BLOCKS__

__BEGIN_DECLS

XPC_DECL(xpc_activity);
XPC_EXPORT XPC_TYPE(_xpc_type_activity);
#define XPC_TYPE_ACTIVITY (&_xpc_type_activity)

enum {
    XPC_ACTIVITY_STATE_RUN = 2
};
typedef long xpc_activity_state_t;

typedef void (^xpc_activity_handler_t)(xpc_activity_t activity);

XPC_EXPORT const char * XPC_ACTIVITY_ALLOW_BATTERY;
XPC_EXPORT const xpc_object_t XPC_ACTIVITY_CHECK_IN;
XPC_EXPORT const char * XPC_ACTIVITY_DELAY;
XPC_EXPORT const char * XPC_ACTIVITY_GRACE_PERIOD;
XPC_EXPORT const char * XPC_ACTIVITY_PRIORITY;
XPC_EXPORT const char * XPC_ACTIVITY_PRIORITY_MAINTENANCE;
XPC_EXPORT const char * XPC_ACTIVITY_PRIORITY_UTILITY;
XPC_EXPORT const char * XPC_ACTIVITY_REPEATING;
XPC_EXPORT const char * XPC_ACTIVITY_INTERVAL;
XPC_EXPORT const char * XPC_ACTIVITY_REQUIRE_NETWORK_CONNECTIVITY;
// Compatibility SPI used by CloudTelemetryShared.
XPC_EXPORT const char * XPC_ACTIVITY_NETWORK_UPLOAD_SIZE;

xpc_activity_state_t xpc_activity_get_state(xpc_activity_t activity);
void xpc_activity_register(const char *identifier, xpc_object_t criteria, xpc_activity_handler_t handler);
void xpc_activity_unregister(const char *identifier);

__END_DECLS

#endif

#endif // __XPC_ACTIVITY_H__ 

