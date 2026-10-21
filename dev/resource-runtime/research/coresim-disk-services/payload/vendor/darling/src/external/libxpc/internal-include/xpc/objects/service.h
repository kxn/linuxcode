/**
 * This file is part of Darling.
 *
 * Copyright (C) 2021 Darling developers
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

#ifndef _XPC_OBJECTS_SERVICE_H_
#define _XPC_OBJECTS_SERVICE_H_

#import <xpc/objects/base.h>
#import <dispatch/dispatch.h>

XPC_CLASS_DECL(service);

struct xpc_service_s {
	struct xpc_object_s base;
	char* name;
	uint64_t handle;
	int kind;
	uint32_t domain;
	dispatch_queue_t queue;
};

@interface XPC_CLASS_INTERFACE(service)
- (instancetype)initWithName: (const char*)name kind: (int)kind domain: (uint32_t)domain
                      handle: (uint64_t)handle queue: (dispatch_queue_t)queue;
@end

#endif // _XPC_OBJECTS_SERVICE_H_
