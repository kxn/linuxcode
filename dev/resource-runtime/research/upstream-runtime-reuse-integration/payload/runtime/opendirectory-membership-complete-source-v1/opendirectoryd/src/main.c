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

#include <xpc/xpc.h>
#include <dispatch/dispatch.h>
#include <stdlib.h>
#include <opendirectory/odipc.h>
#include <errno.h>
#include <membership.h>
#include <membershipPriv.h>
#include <pwd.h>
#include <limits.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "identifier-translation.h"
#include "local-membership-check.h"

#include "log.h"

#define GET_LOG(_name) os_log_t _name ## _get_log(void) { \
		static dispatch_once_t once_token; \
		static os_log_t log = NULL; \
		dispatch_once(&once_token, ^{ \
			log = os_log_create("com.apple.opendirectoryd", #_name); \
			if (!log) { \
				abort(); \
			} \
		}); \
		return log; \
	};

GET_LOG(general);
GET_LOG(membership);

// ODD = *O*pen*D*irectory*D*

#define ODD_PRIVATE_RPC_SERVICE_NAME "com.apple.private.opendirectoryd.rpc"
#define ODD_LIBINFO_LEGACY_SERVICE_NAME "com.apple.system.DirectoryService.libinfo_v1"
#define ODD_MEMBERSHIP_LEGACY_SERVICE_NAME "com.apple.system.DirectoryService.membership_v1"
#define ODD_API_SERVICE_NAME "com.apple.system.opendirectoryd.api"
#define ODD_LIBINFO_SERVICE_NAME "com.apple.system.opendirectoryd.libinfo"
#define ODD_MEMBERSHIP_SERVICE_NAME "com.apple.system.opendirectoryd.membership"

#define ODD_MEMBERSHIP_CURRENT_RPC_VERSION 2

static dispatch_queue_t membership_service_queue = NULL;
static xpc_connection_t membership_service_listener = NULL;

static void membership_send_reply(xpc_object_t request, xpc_object_t reply) {
    if (!reply) return;
    xpc_connection_t connection = xpc_dictionary_get_remote_connection(request);
    if (connection) xpc_connection_send_message(connection, reply);
    xpc_release(reply);
}

static void membership_reply_with_error(xpc_object_t request, int error) {
    xpc_object_t reply = xpc_dictionary_create_reply(request);
    if (!reply) return;
    xpc_dictionary_set_int64(reply, OD_RPC_ERROR, error);
    membership_send_reply(request, reply);
}

static bool read_integer(xpc_object_t message, const char *key, int *result) {
    xpc_object_t value = xpc_dictionary_get_value(message, key);
    if (!value || xpc_get_type(value) != XPC_TYPE_INT64) return false;
    int64_t number = xpc_int64_get_value(value);
    if (number < INT_MIN || number > INT_MAX) return false;
    *result = (int)number;
    return true;
}

static bool read_data(xpc_object_t message, const char *key, const void **result, size_t *size) {
    xpc_object_t value = xpc_dictionary_get_value(message, key);
    if (!value || xpc_get_type(value) != XPC_TYPE_DATA) return false;
    *size = xpc_data_get_length(value);
    if (!*size || *size > 1024 * 1024) return false;
    *result = xpc_data_get_bytes_ptr(value);
    return *result != NULL;
}

static void rpc_mbr_identifier_translate(xpc_object_t message) {
    int target, type, kind;
    const void *identifier;
    size_t size;
    if (!read_integer(message, "requesting", &target) || !read_integer(message, "type", &type) ||
        !read_data(message, "identifier", &identifier, &size)) {
        membership_reply_with_error(message, EINVAL);
        return;
    }
    void *result = NULL;
    size_t result_size = 0;
    int status = od_identifier_resolve(type, identifier, size, target, &result, &result_size, &kind);
    if (status) { membership_reply_with_error(message, status); return; }
    xpc_object_t reply = xpc_dictionary_create_reply(message);
    if (reply) {
        xpc_dictionary_set_data(reply, "identifier", result, result_size);
        xpc_dictionary_set_int64(reply, "rectype", kind);
        xpc_dictionary_set_int64(reply, OD_RPC_ERROR, 0);
    }
    free(result);
    membership_send_reply(message, reply);
}

static void membership_reply_result(xpc_object_t message, int status, int member) {
    if (status) { membership_reply_with_error(message, status); return; }
    xpc_object_t reply = xpc_dictionary_create_reply(message);
    if (!reply) return;
    xpc_dictionary_set_int64(reply, OD_RPC_ERROR, 0);
    xpc_dictionary_set_bool(reply, "ismember", member != 0);
    membership_send_reply(message, reply);
}

static void rpc_mbr_check_service_membership(xpc_object_t message) {
    int user_type;
    const void *user;
    size_t user_size;
    xpc_object_t service_value = xpc_dictionary_get_value(message, "service");
    if (!read_integer(message, "user_idtype", &user_type) || !read_data(message, "user_id", &user, &user_size) ||
        !service_value || xpc_get_type(service_value) != XPC_TYPE_STRING) {
        membership_reply_with_error(message, EINVAL);
        return;
    }
    const char *service = xpc_string_get_string_ptr(service_value);
    if (!service || !*service) { membership_reply_with_error(message, EINVAL); return; }
    int member = 0;
    int status = linuxcode_check_service_membership(user_type, user, user_size, service, &member);
    membership_reply_result(message, status, member);
}

static void rpc_mbr_check_membership(xpc_object_t message) {
    int user_type, group_type;
    const void *user, *group;
    size_t user_size, group_size;
    xpc_object_t refresh = xpc_dictionary_get_value(message, "refresh");
    if (!read_integer(message, "user_idtype", &user_type) || !read_integer(message, "group_idtype", &group_type) ||
        !read_data(message, "user_id", &user, &user_size) || !read_data(message, "group_id", &group, &group_size) ||
        !refresh || xpc_get_type(refresh) != XPC_TYPE_BOOL) {
        membership_reply_with_error(message, EINVAL);
        return;
    }
    int member = 0;
    int status = linuxcode_check_membership(user_type, user, user_size, group_type, group, group_size,
                                           xpc_bool_get_value(refresh), &member);
    membership_reply_result(message, status, member);
}

static void rpc_mbr_set_identifier_ttl(xpc_object_t message) {
    /* This local backend performs fresh lookups and has no identifier cache. */
    membership_reply_with_error(message, ENOSYS);
}

static void rpc_mbr_cache_flush(xpc_object_t message) {
    /* There is no cache to retain stale records: flush is already complete. */
    membership_reply_with_error(message, 0);
}

static void handle_new_membership_connection(xpc_connection_t connection) {
	xpc_connection_set_event_handler(connection, ^(xpc_object_t object) {
		xpc_type_t type = xpc_get_type(object);

		if (type == XPC_TYPE_DICTIONARY) {
			membership_log_debug("membership connection received dictionary: %@", object);

			int rpc_version = 0;

			if (!read_integer(object, OD_RPC_VERSION, &rpc_version) || rpc_version != ODD_MEMBERSHIP_CURRENT_RPC_VERSION) {
				membership_log_error("invalid RPC version %d in message: %@", rpc_version, object);
				membership_reply_with_error(object, EINVAL);
				return;
			}

			const char* rpc_name = xpc_dictionary_get_string(object, OD_RPC_NAME);

			if (!rpc_name) {
				membership_log_error("no RPC procedure name in message: %@", object);
				membership_reply_with_error(object, EINVAL);
                return;
			}

			membership_log_debug("RPC procedure call message: %@", object);

			if (strcmp(rpc_name, "mbr_identifier_translate") == 0) {
				rpc_mbr_identifier_translate(object);
			} else if (strcmp(rpc_name, "mbr_check_service_membership") == 0) {
				rpc_mbr_check_service_membership(object);
			} else if (strcmp(rpc_name, "mbr_set_identifier_ttl") == 0) {
				rpc_mbr_set_identifier_ttl(object);
			} else if (strcmp(rpc_name, "mbr_check_membership") == 0) {
				rpc_mbr_check_membership(object);
			} else if (strcmp(rpc_name, "mbr_cache_flush") == 0) {
				rpc_mbr_cache_flush(object);
			} else {
				membership_log_error("invalid RPC procedure name \"%s\" in message: %@", rpc_name, object);
				membership_reply_with_error(object, EINVAL);
			}
		} else if (type == XPC_TYPE_ERROR) {
			if (object == XPC_ERROR_CONNECTION_INVALID) {
				membership_log_debug("membership connection invalidated");
			} else {
				membership_log_error("membership connection received XPC error: %@", object);
			}
		} else {
			membership_log_error("unknown XPC object received in service listener: %@", object);
		}
	});
	xpc_connection_resume(connection);
};

int main(int argc, char** argv) {
	membership_service_queue = dispatch_queue_create(ODD_MEMBERSHIP_SERVICE_NAME, DISPATCH_QUEUE_CONCURRENT);
	if (!membership_service_queue) {
		abort();
	}

	membership_service_listener = xpc_connection_create_mach_service(ODD_MEMBERSHIP_SERVICE_NAME, membership_service_queue, XPC_CONNECTION_MACH_SERVICE_LISTENER);
	if (!membership_service_listener) {
		abort();
	}

	xpc_connection_set_event_handler(membership_service_listener, ^(xpc_object_t object) {
		xpc_type_t type = xpc_get_type(object);

		if (type == XPC_TYPE_CONNECTION) {
			handle_new_membership_connection(object);
		} else if (type == XPC_TYPE_ERROR) {
			general_log_error("service listener received XPC error: %@", object);
		} else {
			general_log_error("unknown XPC object received in service listener: %@", object);
		}
	});

	xpc_connection_resume(membership_service_listener);

	dispatch_main();
	return 0;
};
