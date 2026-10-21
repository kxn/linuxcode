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

#import <xpc/objects/service.h>
#import <xpc/objects/service_instance.h>
#import <xpc/util.h>
#import <xpc/xpc.h>
#import <xpc/private/service.h>
#include <uuid/uuid.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

XPC_CLASS_SYMBOL_DECL(service);

OS_OBJECT_NONLAZY_CLASS
@implementation XPC_CLASS(service)

XPC_CLASS_HEADER(service);

- (instancetype)initWithName: (const char*)name kind: (int)kind domain: (uint32_t)domain
                      handle: (uint64_t)handle queue: (dispatch_queue_t)queue {
	if ((self = [super init])) {
		XPC_THIS_DECL(service);
		char generated[37];
		if (!name) {
			uuid_t identifier; uuid_generate(identifier); uuid_unparse(identifier, generated);
			name = generated;
		}
		this->name = strdup(name);
		if (!this->name) { [self release]; return nil; }
		this->kind = kind; this->domain = domain; this->handle = handle;
		if (queue) { dispatch_retain(queue); this->queue = queue; }
		else this->queue = dispatch_queue_create("com.darling.xpc.service", NULL);
		if (!this->queue) { [self release]; return nil; }
	}
	return self;
}

- (void)dealloc {
	XPC_THIS_DECL(service);
	free(this->name);
	if (this->queue) dispatch_release(this->queue);
	[super dealloc];
}

@end

//
// private C API
//

XPC_EXPORT
void xpc_service_attach(xpc_service_t xservice, bool run, bool kill) {
	xpc_stub();
};

XPC_EXPORT
xpc_object_t xpc_service_create(int kind, const char* name, uint64_t handle, dispatch_queue_t queue) {
	return [[XPC_CLASS(service) alloc] initWithName: name kind: kind
		domain: kind == 1 ? 5 : 6 handle: handle queue: queue];
};

XPC_EXPORT
xpc_object_t xpc_service_create_from_specifier(const char* specifier, dispatch_queue_t queue) {
	if (!specifier) return NULL;
	char* storage = strdup(specifier);
	if (!storage) return NULL;
	char* cursor = storage;
	char* domain_name = strsep(&cursor, "/");
	char* second = strsep(&cursor, "/");
	char* third = strsep(&cursor, "/");
	uint32_t domain = 0; uint64_t handle = 0; const char* name = NULL;
	if (!strcmp(domain_name, "system")) { domain = 1; name = second; }
	else if (!strcmp(domain_name, "loginwindow")) { domain = 2; handle = UINT32_MAX; name = second; }
	else {
		if (!strcmp(domain_name, "user")) domain = 2;
		else if (!strcmp(domain_name, "login")) domain = 3;
		else if (!strcmp(domain_name, "pid")) domain = 5;
		else if (!strcmp(domain_name, "gui")) domain = 8;
		if (domain && second) {
			char* end; handle = strtoull(second, &end, 10);
			if (*end || handle > INT64_MAX - 1) domain = 0;
			name = third;
		} else domain = 0;
	}
	xpc_object_t result = NULL;
	if (domain && name && *name) result = [[XPC_CLASS(service) alloc]
		initWithName: name kind: 3 domain: domain handle: handle queue: queue];
	free(storage);
	return result;
};

XPC_EXPORT
const char* xpc_service_get_rendezvous_token(xpc_object_t xservice) {
	TO_OBJC_CHECKED(service, xservice, object) {
		return ((struct xpc_service_s*)object)->name;
	}
	return NULL;
};

XPC_EXPORT
int xpc_service_kickstart(xpc_object_t xservice, bool suspended, bool kill) {
	return xpc_service_kickstart_with_flags(xservice, (suspended ? 1 : 0) | (kill ? 2 : 0));
};

XPC_EXPORT
int xpc_service_kickstart_with_flags(xpc_object_t xservice, uint64_t flags) {
	TO_OBJC_CHECKED_ON_FAIL(service, xservice, object) { return EINVAL; }
	struct xpc_service_s* service = (struct xpc_service_s*)object;
	xpc_object_t request = xpc_dictionary_create(NULL, NULL, 0), reply = NULL;
	if (!request) return ENOMEM;
	xpc_dictionary_set_uint64(request, "type", service->domain);
	xpc_dictionary_set_uint64(request, "handle", service->handle);
	xpc_dictionary_set_string(request, "name", service->name);
	xpc_dictionary_set_bool(request, "unidomain", true);
	xpc_dictionary_set_bool(request, "suspended", flags & 1);
	xpc_dictionary_set_bool(request, "kill", flags & 2);
	xpc_dictionary_set_bool(request, "unthrottle", true);
	int error = _xpc_service_routine(XPC_SERVICE_KICKSTART, request, &reply);
	if (reply) xpc_release(reply);
	xpc_release(request);
	return error;
};

XPC_EXPORT
void xpc_service_set_attach_handler(xpc_service_t xservice, void (^handler)(xpc_service_instance_t xinstance)) {
	xpc_stub();
};

XPC_EXPORT
void _xpc_service_last_xref_cancel(xpc_service_t xservice) {
	xpc_stub();
};

XPC_EXPORT
void xpc_handle_service() {
	// i have no clue what the types for the 3 arguments to this function are
	xpc_stub();
};

XPC_EXPORT
void xpc_handle_subservice() {
	// same as for `xpc_handle_service`
	xpc_stub();
};
