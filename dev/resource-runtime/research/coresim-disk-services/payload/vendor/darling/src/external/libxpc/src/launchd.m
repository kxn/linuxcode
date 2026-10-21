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

#import <xpc/xpc.h>
#import <launch.h>
#import <xpc/util.h>
#import <xpc/private.h>
#import <xpc/private/launch_service_stats.h>
#import <xpc/private/service.h>
#import <xpc/objects/pipe.h>
#import <xpc/objects/dictionary.h>
#import <xpc/objects/bundle.h>
#import <xpc/objects/string.h>
#include <mach/mach_vm.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>

_Static_assert(sizeof(struct launch_service_stats_record) == 59, "native launch record ABI");
_Static_assert(sizeof(struct launch_service_stats) == 24, "native launch result ABI");

static int launchd_routine(int subsystem, int routine, xpc_object_t request, xpc_object_t* reply) {
	if (!reply || xpc_get_type(request) != (xpc_type_t)XPC_TYPE_DICTIONARY) return EINVAL;
	*reply = NULL;
	xpc_dictionary_set_uint64(request, "subsystem", subsystem);
	xpc_dictionary_set_uint64(request, "routine", routine);
	/* Explicitly opt in: job dictionaries may contain application data. */
	const char* trace = getenv("DARLING_XPC_TRACE_LAUNCH_JOBS");
	if (subsystem == 10 && trace && strcmp(trace, "1") == 0) {
		char* description = xpc_copy_description(request);
		fprintf(stderr, "DARLING_XPC_LAUNCH_JOB_REQUEST %s\n", description ?: "(unavailable)");
		free(description);
	}
	@autoreleasepool {
		XPC_CLASS(pipe)* pipe = [[XPC_CLASS(pipe) alloc] initWithBootstrapPort: bootstrap_port];
		if (!pipe) return EPIPE;
		xpc_object_t response = NULL;
		int error = [pipe sendMessage: (id)request withSynchronousReply: &response flags: 0 timeout: 5000];
		[pipe release];
		if (!error && !response) error = EPROTO;
		if (!error) {
			audit_token_t token;
			xpc_dictionary_get_audit_token(response, &token);
			if (token.val[5] != 1 || token.val[1] != 0) error = EPERM;
		}
		if (!error) error = (int)xpc_dictionary_get_int64(response, "error");
		if (error) { if (response) xpc_release(response); return error; }
		*reply = response;
		return 0;
	}
}

/* The original Intel job wrappers select subsystem 10; domain uses 3.
 * The asynchronous ABI
 * carries a Mach reply port as its third argument, not a block or queue. */
XPC_EXPORT
int _xpc_domain_routine(int routine, xpc_object_t request, xpc_object_t* reply) {
	return launchd_routine(3, routine, request, reply);
}

XPC_EXPORT
int _launch_job_routine(int routine, xpc_object_t request, xpc_object_t* reply) {
	if (!reply || xpc_get_type(request) != (xpc_type_t)XPC_TYPE_DICTIONARY) return EINVAL;
	*reply = NULL;
	xpc_object_t forwarded = xpc_retain(request);
	/* A submitted child starts in launchd rather than in the client's process
	 * tree. Carry explicit Darling loader scopes just as User bundle jobs do.
	 * Copy both dictionaries so the caller's plist/environment stay unchanged. */
	xpc_object_t plist = xpc_dictionary_get_value(request, "plist");
	if (routine == 1011 && xpc_get_type(plist) == (xpc_type_t)XPC_TYPE_DICTIONARY) {
		const char* keys[] = { "DARLING_DYLD_OVERRIDE_EXECUTABLES",
			"DARLING_DYLD_OVERRIDE_LIBRARY_PATH", "DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH",
			"DARLING_XPC_TRACE_LAUNCH_JOBS" };
		xpc_object_t environment = NULL;
		for (size_t i = 0; i < sizeof(keys)/sizeof(*keys); ++i) {
			const char* value = getenv(keys[i]);
			if (!value) continue;
			if (!environment) {
				xpc_object_t original = xpc_dictionary_get_value(plist, "EnvironmentVariables");
				if (original && xpc_get_type(original) != (xpc_type_t)XPC_TYPE_DICTIONARY) {
					xpc_release(forwarded); return EINVAL;
				}
				environment = original ? [(XPC_CLASS(dictionary)*)original copy] : xpc_dictionary_create(NULL, NULL, 0);
			}
			xpc_dictionary_set_string(environment, keys[i], value);
		}
		if (environment) {
			xpc_object_t scoped_plist = [(XPC_CLASS(dictionary)*)plist copy];
			xpc_dictionary_set_value(scoped_plist, "EnvironmentVariables", environment);
			xpc_release(forwarded); forwarded = [(XPC_CLASS(dictionary)*)request copy];
			xpc_dictionary_set_value(forwarded, "plist", scoped_plist);
			xpc_release(scoped_plist); xpc_release(environment);
		}
	}
	int error = launchd_routine(10, routine, forwarded, reply);
	xpc_release(forwarded);
	return error;
}

XPC_EXPORT
int _launch_job_routine_async(int routine, xpc_object_t request, mach_port_t reply_port) {
	if (xpc_get_type(request) != (xpc_type_t)XPC_TYPE_DICTIONARY) return EINVAL;
	xpc_dictionary_set_uint64(request, "subsystem", 10);
	xpc_dictionary_set_uint64(request, "routine", routine);
	@autoreleasepool {
		XPC_CLASS(pipe)* pipe = [[XPC_CLASS(pipe) alloc] initWithBootstrapPort: bootstrap_port];
		if (!pipe) return EPIPE;
		int error = [pipe sendMessage: (id)request withReplyPort: reply_port];
		[pipe release];
		return error;
	}
}

XPC_EXPORT
int _xpc_control_routine(int routine, xpc_object_t request, xpc_object_t* reply) {
	return launchd_routine(XPC_LAUNCH_STATS_SUBSYSTEM, routine, request, reply);
}

XPC_EXPORT
int _xpc_service_routine(int routine, xpc_object_t request, xpc_object_t* reply) {
	return launchd_routine(XPC_SERVICE_SUBSYSTEM, routine, request, reply);
}

static int launch_stats_simple(const char* monitor_id, uint32_t capacity, int routine, bool* enabled) {
	if (!monitor_id || !*monitor_id) return EINVAL;
	xpc_object_t request = xpc_dictionary_create(NULL, NULL, 0), reply = NULL;
	if (!request) return ENOMEM;
	xpc_dictionary_set_string(request, "monitor_id", monitor_id);
	if (routine == XPC_LAUNCH_STATS_ENABLE) xpc_dictionary_set_uint64(request, "capacity", capacity);
	int error = _xpc_control_routine(routine, request, &reply);
	if (!error && enabled) *enabled = xpc_dictionary_get_bool(reply, "enabled");
	if (reply) xpc_release(reply);
	xpc_release(request);
	return error;
}

XPC_EXPORT
int launch_service_stats_enable(const char* monitor_id, uint32_t capacity) {
	if (!capacity) return EINVAL;
	return launch_stats_simple(monitor_id, capacity, XPC_LAUNCH_STATS_ENABLE, NULL);
}

XPC_EXPORT
int launch_service_stats_disable(const char* monitor_id) {
	return launch_stats_simple(monitor_id, 0, XPC_LAUNCH_STATS_DISABLE, NULL);
}

XPC_EXPORT
bool launch_service_stats_is_enabled(const char* monitor_id) {
	bool enabled = false;
	return launch_stats_simple(monitor_id, 0, XPC_LAUNCH_STATS_QUERY, &enabled) == 0 && enabled;
}

XPC_EXPORT
int _launch_service_stats_copy_impl(const char* monitor_id, uint32_t capacity,
		struct launch_service_stats* result, uint32_t version) {
	static const size_t strides[] = {37, 45, 49, 51, 59};
	if (!monitor_id || !*monitor_id || !result || version < 2 || version > 6 || !capacity) return EINVAL;
	// Bound physical page conversion in this backend; do not try to populate
	// hundreds of GB for a malicious uint32 capacity.
	if (capacity > (1U << 20)) return ENOMEM;
	size_t page = getpagesize(), length = ((size_t)capacity * 59 + page - 1) & ~(page - 1);
	mach_vm_address_t buffer = 0;
	kern_return_t status = mach_vm_allocate(mach_task_self(), &buffer, length, VM_FLAGS_ANYWHERE);
	if (status != KERN_SUCCESS) return ENOMEM;
	xpc_object_t shmem = xpc_shmem_create((void*)buffer, length);
	if (!shmem) { mach_vm_deallocate(mach_task_self(), buffer, length); return ENOTSUP; }
	xpc_object_t request = xpc_dictionary_create(NULL, NULL, 0), reply = NULL;
	if (!request) { xpc_release(shmem); mach_vm_deallocate(mach_task_self(), buffer, length); return ENOMEM; }
	xpc_dictionary_set_string(request, "monitor_id", monitor_id);
	xpc_dictionary_set_value(request, "shmem", shmem);
	xpc_release(shmem);
	int error = _xpc_control_routine(XPC_LAUNCH_STATS_COPY, request, &reply);
	struct launch_service_stats output = {0};
	if (!error) {
		uint64_t count = xpc_dictionary_get_uint64(reply, "count");
		uint64_t dropped = xpc_dictionary_get_uint64(reply, "dropped-count");
		xpc_object_t labels = xpc_dictionary_get_value(reply, "labels");
		if (count > length / 59 || count > UINT32_MAX || dropped > UINT32_MAX
			|| xpc_get_type(labels) != (xpc_type_t)XPC_TYPE_ARRAY) error = EPROTO;
		if (!error) {
			output.count = count; output.dropped_count = dropped;
			output.labels = xpc_retain(labels);
			if (count) {
				size_t stride = strides[version - 2];
				output.records = malloc(count * stride);
				if (!output.records) error = ENOMEM;
				else for (size_t i = 0; i < count; ++i) {
					memcpy((char*)output.records + i * stride, (char*)buffer + i * 59, stride);
				}
			}
		}
	}
	if (reply) xpc_release(reply);
	xpc_release(request);
	mach_vm_deallocate(mach_task_self(), buffer, length);
	if (error) { if (output.labels) xpc_release(output.labels); free(output.records); }
	else *result = output;
	return error;
}

//
// private C API
//

struct some_launch_service_stats_struct;

XPC_EXPORT
xpc_object_t _launch_msg2(xpc_object_t request, int type, uint64_t handle) {
	// `request` is probably a dictionary
	// valid values for `type`: 0, 1, 2, 3
	// `handle` can be a normal value or it can be UINT64_MAX (only matters when `type` == )
	// returns a uint64 object
	xpc_stub();
	return NULL;
};

XPC_EXPORT
int _launch_service_stats_copy_4ppse_impl(struct some_launch_service_stats_struct* launch_service_stats, int type) {
	// no clue what the structure layout is
	// `type` MUST be 2 or else the function crashes
	// the return type seems to be a status code
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_activate_socket(const char* key, int** fds, size_t* count) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_add_external_service(int handle, const char* path, xpc_object_t overlay) {
	// `overlay` is probably a dictionary
	// no clue what type of value `handle` is other than some integer
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_bootout_user_service_4coresim(const char* name) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
xpc_object_t launch_copy_busy_extension_instances(const char** names, size_t name_count) {
	// returns an array
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t launch_copy_endpoints_properties_for_pid(pid_t pid) {
	// returns a dictionary
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t launch_copy_extension_properties(xpc_connection_t xconn) {
	// returns a dictionary
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t launch_copy_extension_properties_for_pid(pid_t pid) {
	// returns a dictionary
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t launch_copy_properties_for_pid_4assertiond(pid_t pid) {
	// returns a dictionary
	xpc_stub();
	return NULL;
};

XPC_EXPORT
int launch_create_persona(uid_t uid, uint64_t flags) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_destroy_persona(int handle) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_disable_directory(const char* path) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_enable_directory(const char* path) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
void launch_extension_check_in_live_4UIKit(void) {
	xpc_stub();
};

XPC_EXPORT const char* launch_extension_property_bundle_id = "XPCExtensionBundleIdentifier";
XPC_EXPORT const char* launch_extension_property_host_bundle_id = "XPCExtensionHostBundleIdentifier";
XPC_EXPORT const char* launch_extension_property_host_pid = "XPCExtensionHostPID";
XPC_EXPORT const char* launch_extension_property_path = "XPCExtensionPath";
XPC_EXPORT const char* launch_extension_property_pid = "XPCExtensionPID";
XPC_EXPORT const char* launch_extension_property_version = "XPCExtensionBundleVersion";
XPC_EXPORT const char* launch_extension_property_xpc_bundle = "XPCExtensionXPCBundle";

XPC_EXPORT
int launch_get_service_enabled(const char* name, bool* out_loaded, bool* out_enabled) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_get_system_service_enabled(const char* name, bool* out_loaded, bool* out_enabled) {
	xpc_stub();
	return -1;
};

/* Resolve metadata from the job launchd actually registered. Querying a
 * random installed bundle must not report a service as registered. */
static char* user_service_bundle_metadata(const char* name, bool version)
{
	if (!name || !name[0]) { errno = EINVAL; return NULL; }
	launch_data_t request = launch_data_alloc(LAUNCH_DATA_DICTIONARY);
	if (!request) { errno = ENOMEM; return NULL; }
	launch_data_dict_insert(request, launch_data_new_string(name), LAUNCH_KEY_GETJOB);
	launch_data_t reply = launch_msg(request);
	launch_data_free(request);
	if (!reply) return NULL;
	char* result = NULL;
	int error = ENOENT;
	if (launch_data_get_type(reply) == LAUNCH_DATA_DICTIONARY) {
		launch_data_t program = launch_data_dict_lookup(reply, LAUNCH_JOBKEY_PROGRAM);
		if (program && launch_data_get_type(program) == LAUNCH_DATA_STRING) {
			@autoreleasepool {
				XPC_CLASS(string)* path = [[XPC_CLASS(string) alloc] initWithCString: launch_data_get_string(program)];
				XPC_CLASS(bundle)* bundle = [[XPC_CLASS(bundle) alloc] initWithPath: path];
				[path release];
				[bundle resolve];
				const char* value = version ? [bundle.infoDictionary stringForKey: "CFBundleVersion"].CString : bundle.bundlePath.CString;
				if (!bundle.error && value) { result = strdup(value); error = result ? 0 : ENOMEM; }
				[bundle release];
			}
		}
	} else if (launch_data_get_type(reply) == LAUNCH_DATA_ERRNO) {
		error = launch_data_get_errno(reply);
		if (!error) error = ENOENT;
	}
	launch_data_free(reply);
	errno = error;
	return result;
}

XPC_EXPORT
char* launch_path_for_user_service_4coresim(const char* name) {
	return user_service_bundle_metadata(name, false);
};

XPC_EXPORT const char* launch_perfcheck_property_endpoint_active = "XPCServiceEndpointActive";
XPC_EXPORT const char* launch_perfcheck_property_endpoint_event = "XPCServiceEndpointEvent";
XPC_EXPORT const char* launch_perfcheck_property_endpoint_name = "XPCServiceEndpointName";
XPC_EXPORT const char* launch_perfcheck_property_endpoint_needs_activation = "XPCServiceEndpointNeedsActivation";
XPC_EXPORT const char* launch_perfcheck_property_endpoints = "XPCServiceEndpoints";

XPC_EXPORT
void launch_remove_external_service(const char* name, const char* version, dispatch_queue_t queue, void (^callback)(int error)) {
	xpc_stub();
};

XPC_EXPORT
int launch_service_stats_disable_4ppse(void) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_service_stats_enable_4ppse(void) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
bool launch_service_stats_is_enabled_4ppse() {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_set_service_enabled(const char* name, bool enabled) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
int launch_set_system_service_enabled(const char* name, bool enabled) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
char* launch_version_for_user_service_4coresim(const char* name) {
	return user_service_bundle_metadata(name, true);
};

xpc_object_t ld2xpc(launch_data_t data);

static void launch_data_dict_iterator(launch_data_t value, const char* key, void* context) {
	xpc_object_t* result = context;
	xpc_object_t xpc_value = ld2xpc(value);
	xpc_dictionary_set_value(*result, key, xpc_value);
};

// this function isn't present in the official libxpc,
// so i'm guessing that it's actually an inline function
XPC_EXPORT
xpc_object_t ld2xpc(launch_data_t data) {
	xpc_object_t result = NULL;

	switch (launch_data_get_type(data)) {
		case LAUNCH_DATA_DICTIONARY: {
			result = xpc_dictionary_create(NULL, NULL, 0);
			launch_data_dict_iterate(data, launch_data_dict_iterator, &result);
		} break;

		case LAUNCH_DATA_ARRAY: {
			size_t length = launch_data_array_get_count(data);
			result = xpc_array_create(NULL, 0);
			for (size_t i = 0; i < length; ++i) {
				xpc_array_append_value(result, ld2xpc(launch_data_array_get_index(data, i)));
			}
		} break;

		case LAUNCH_DATA_FD: {
			result = xpc_fd_create(launch_data_get_fd(data));
		} break;

		case LAUNCH_DATA_INTEGER: {
			result = xpc_int64_create(launch_data_get_integer(data));
		} break;

		case LAUNCH_DATA_REAL: {
			result = xpc_double_create(launch_data_get_real(data));
		} break;

		case LAUNCH_DATA_BOOL: {
			result = xpc_bool_create(launch_data_get_bool(data));
		} break;

		case LAUNCH_DATA_STRING: {
			result = xpc_string_create(launch_data_get_string(data));
		} break;

		case LAUNCH_DATA_OPAQUE: {
			result = xpc_data_create(launch_data_get_opaque(data), launch_data_get_opaque_size(data));
		} break;

		case LAUNCH_DATA_ERRNO: {
			result = xpc_int64_create(launch_data_get_errno(data));
		} break;

		case LAUNCH_DATA_MACHPORT: {
			// NOTE: i have verified that the contained port does in fact always hold a receive right, so this is the right XPC class to use
			result = xpc_mach_recv_create(launch_data_get_machport(data));
		} break;
	}

	return result;
};

XPC_EXPORT
kern_return_t xpc_call_wakeup(mach_port_t port, int status) {
	xpc_stub();
	return -1;
};
