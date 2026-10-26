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
#import <xpc/util.h>
#import <mach-o/dyld_priv.h>
#define __DISPATCH_INDIRECT__
#import <dispatch/mach_private.h>
#import <os/voucher_private.h>

#include <sys/sysctl.h>

#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <xpc/private.h>
#include <libproc.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>

/* Read signature metadata matching the loaded executable. This does not
 * implement certificate trust or kernel entitlement enforcement. */
static unsigned char *self_entitlement_xml;
static size_t self_entitlement_xml_size;
static dispatch_once_t self_entitlement_once;
static uint32_t self_signature_be32(const unsigned char *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static uint64_t self_signature_be64(const unsigned char *p) {
    return ((uint64_t)self_signature_be32(p)<<32)|self_signature_be32(p+4);
}
static bool self_signature_read(int fd, void *out, size_t size, uint64_t offset, uint64_t limit) {
    if (offset>limit || size>limit-offset || offset>INT64_MAX || size>INT64_MAX-offset) return false;
    unsigned char *p=out;
    while (size) {
        ssize_t n=pread(fd,p,size,(off_t)offset);
        if (n<0 && errno==EINTR) continue;
        if (n<=0) return false;
        p+=n;size-=n;offset+=n;
    }
    return true;
}
static void signature_load_entitlements(int fd, const struct mach_header_64 *live,
    unsigned char **xml, size_t *xml_size) {
    if (!live || live->magic!=MH_MAGIC_64 || live->sizeofcmds>16*1024*1024 || live->ncmds>16384) {close(fd);return;}
    unsigned char *commands=NULL,*signature=NULL;struct stat st;
    if (fstat(fd,&st) || st.st_size<32) goto done;
    uint64_t total=(uint64_t)st.st_size,base=0,length=total;unsigned char head[8];
    if (!self_signature_read(fd,head,sizeof(head),0,total)) goto done;
    uint32_t fat=self_signature_be32(head);
    if (fat==0xcafebabe || fat==0xcafebabf) {
        uint32_t count=self_signature_be32(head+4);size_t stride=fat==0xcafebabe?20:32;
        if (!count || count>4096 || (uint64_t)count*stride>total-8) goto done;
        bool found=false;
        for (uint32_t i=0;i<count;++i) {
            unsigned char arch[32];if (!self_signature_read(fd,arch,stride,8+(uint64_t)i*stride,total)) goto done;
            if (self_signature_be32(arch)!=(uint32_t)live->cputype ||
                (self_signature_be32(arch+4)&0xffffff)!=((uint32_t)live->cpusubtype&0xffffff)) continue;
            if (found) goto done;
            found=true;base=stride==20?self_signature_be32(arch+8):self_signature_be64(arch+8);
            length=stride==20?self_signature_be32(arch+12):self_signature_be64(arch+16);
        }
        if (!found || base>total || length>total-base) goto done;
    }
    struct mach_header_64 disk;
    if (!self_signature_read(fd,&disk,sizeof(disk),base,total) || disk.magic!=MH_MAGIC_64 ||
        disk.cputype!=live->cputype || disk.cpusubtype!=live->cpusubtype || disk.ncmds!=live->ncmds ||
        disk.sizeofcmds!=live->sizeofcmds || length<sizeof(disk) || disk.sizeofcmds>length-sizeof(disk)) goto done;
    commands=malloc(disk.sizeofcmds);if (!commands || !self_signature_read(fd,commands,disk.sizeofcmds,base+sizeof(disk),total)) goto done;
    const unsigned char *live_commands=(const unsigned char *)(live+1);
    size_t at=0;uint32_t sig_offset=0,sig_size=0;bool has_signature=false;
    for (uint32_t i=0;i<disk.ncmds;++i) {
        if (at>disk.sizeofcmds || disk.sizeofcmds-at<8) goto done;
        struct load_command cmd;memcpy(&cmd,commands+at,sizeof(cmd));
        if (cmd.cmdsize<8 || cmd.cmdsize>disk.sizeofcmds-at || memcmp(commands+at,live_commands+at,cmd.cmdsize)) goto done;
        if (cmd.cmd==LC_CODE_SIGNATURE) {
            if (has_signature || cmd.cmdsize!=sizeof(struct linkedit_data_command)) goto done;
            struct linkedit_data_command s;memcpy(&s,commands+at,sizeof(s));
            sig_offset=s.dataoff;sig_size=s.datasize;has_signature=true;
        }
        at+=cmd.cmdsize;
    }
    if (at!=disk.sizeofcmds || !has_signature || sig_size<12 || sig_size>64*1024*1024 ||
        sig_offset>length || sig_size>length-sig_offset) goto done;
    signature=malloc(sig_size);if (!signature || !self_signature_read(fd,signature,sig_size,base+sig_offset,total)) goto done;
    uint32_t blob_length=self_signature_be32(signature+4),count=self_signature_be32(signature+8);
    if (self_signature_be32(signature)!=0xfade0cc0 || blob_length<12 || blob_length>sig_size || count>(blob_length-12)/8) goto done;
    uint32_t xml_offset=0,xml_length=0;
    for (uint32_t i=0;i<count;++i) {
        const unsigned char *index=signature+12+i*8;uint32_t kind=self_signature_be32(index),offset=self_signature_be32(index+4);
        if (offset<12+(uint64_t)count*8 || offset>blob_length || blob_length-offset<8) goto done;
        uint32_t size=self_signature_be32(signature+offset+4);if (size<8 || size>blob_length-offset) goto done;
        if (kind==5) {
            if (xml_offset || self_signature_be32(signature+offset)!=0xfade7171) goto done;
            xml_offset=offset+8;xml_length=size-8;
        }
    }
    if (xml_offset && xml_length) {
        *xml=malloc(xml_length);
        if (*xml) {memcpy(*xml,signature+xml_offset,xml_length);*xml_size=xml_length;}
    }
done:
    free(signature);free(commands);close(fd);
}
static void self_signature_load_entitlements(void) {
    const struct mach_header_64 *live=(const struct mach_header_64 *)_dyld_get_image_header(0);
    char path[4096];uint32_t path_size=sizeof(path);
    if (_NSGetExecutablePath(path,&path_size)) return;
    int fd=open(path,O_RDONLY|O_CLOEXEC);if (fd<0) return;
    signature_load_entitlements(fd,live,&self_entitlement_xml,&self_entitlement_xml_size);
}
static xpc_object_t self_signature_entitlement_dictionary(void) {
    dispatch_once(&self_entitlement_once, ^{self_signature_load_entitlements();});
    if (!self_entitlement_xml) return NULL;
    xpc_object_t dictionary=xpc_create_from_plist(self_entitlement_xml,self_entitlement_xml_size);
    if (dictionary && xpc_get_type(dictionary)!=XPC_TYPE_DICTIONARY) {xpc_release(dictionary);return NULL;}
    return dictionary;
}

static bool signature_peer_matches(task_t task, const audit_token_t *expected) {
    audit_token_t actual;mach_msg_type_number_t count=TASK_AUDIT_TOKEN_COUNT;
    return task_info(task,TASK_AUDIT_TOKEN,(task_info_t)&actual,&count)==KERN_SUCCESS &&
        count==TASK_AUDIT_TOKEN_COUNT && actual.val[5]==expected->val[5] && actual.val[7]==expected->val[7];
}
static bool signature_remote_read(task_t task, uint64_t address, void *out, size_t size) {
    mach_vm_size_t copied=0;
    return address && address<=UINT64_MAX-size &&
        mach_vm_read_overwrite(task,address,size,(mach_vm_address_t)out,&copied)==KERN_SUCCESS && copied==size;
}
static xpc_object_t peer_signature_entitlement_dictionary(const audit_token_t *token) {
    if (!token || (int32_t)token->val[5]<=0 || !token->val[7] || token->val[7]==UINT32_MAX) return NULL;
    task_t task=MACH_PORT_NULL;
    if (task_for_pid(mach_task_self(),(pid_t)token->val[5],&task)!=KERN_SUCCESS) return NULL;
    unsigned char *live=NULL,*xml=NULL;size_t xml_size=0;xpc_object_t result=NULL;
    struct task_dyld_info dyld;mach_msg_type_number_t count=TASK_DYLD_INFO_COUNT;
    struct {uint32_t version,count;uint64_t images;} infos;
    struct {uint64_t header,path,modified;} first;
    struct mach_header_64 header;
    char path[PROC_PIDPATHINFO_MAXSIZE],after_path[PROC_PIDPATHINFO_MAXSIZE];
    if (!signature_peer_matches(task,token) ||
        proc_pidpath((pid_t)token->val[5],path,sizeof(path))<=0 ||
        task_info(task,TASK_DYLD_INFO,(task_info_t)&dyld,&count)!=KERN_SUCCESS ||
        dyld.all_image_info_format!=TASK_DYLD_ALL_IMAGE_INFO_64 ||
        !signature_remote_read(task,dyld.all_image_info_addr,&infos,sizeof(infos)) || !infos.count || infos.count>16384 ||
        !signature_remote_read(task,infos.images,&first,sizeof(first)) ||
        !signature_remote_read(task,first.header,&header,sizeof(header)) || header.magic!=MH_MAGIC_64 ||
        header.filetype!=MH_EXECUTE || header.sizeofcmds>16*1024*1024 || header.ncmds>16384) goto done;
    live=malloc(sizeof(header)+header.sizeofcmds);
    if (!live || !signature_remote_read(task,first.header,live,sizeof(header)+header.sizeofcmds) ||
        memcmp(live,&header,sizeof(header))) goto done;
    int fd=open(path,O_RDONLY|O_CLOEXEC);if (fd<0) goto done;
    signature_load_entitlements(fd,(const struct mach_header_64 *)live,&xml,&xml_size);
    if (!xml || !signature_peer_matches(task,token) ||
        proc_pidpath((pid_t)token->val[5],after_path,sizeof(after_path))<=0 || strcmp(path,after_path)) goto done;
    result=xpc_create_from_plist(xml,xml_size);
    if (result && xpc_get_type(result)!=XPC_TYPE_DICTIONARY) {xpc_release(result);result=NULL;}
done:
    free(xml);free(live);mach_port_deallocate(mach_task_self(),task);return result;
}

struct os_system_version {
	unsigned int major;
	unsigned int minor;
	unsigned int patch;
};

XPC_EXPORT
struct os_system_version _system_version_fallback = {
	.major = 10,
	.minor = 15,
	.patch = 0,
};

static struct os_system_version current_version = {0};
static dispatch_once_t current_version_once;

XPC_EXPORT
int os_system_version_get_current_version(struct os_system_version* out_version);

XPC_EXPORT
bool _availability_version_check(uint32_t version_count, const dyld_build_version_t* versions) {
	/* The original Intel ABI uses a 32-bit count and eight-byte platform /
	 * packed-version records. An absent platform is unconstrained; the first
	 * matching record decides. This runtime executes macOS host tools. */
	if (version_count && !versions) return false;
	for (uint32_t i = 0; i < version_count; ++i) {
		if (versions[i].platform != PLATFORM_MACOS) continue;
		struct os_system_version running;
		if (os_system_version_get_current_version(&running) || running.major > 65535 ||
		    running.minor > 255 || running.patch > 255) return false;
		uint32_t packed = (running.major << 16) | (running.minor << 8) | running.patch;
		return versions[i].version <= packed;
	}
	return true;
};

XPC_EXPORT
int _system_ios_support_version_copy_string_sysctl(char* out_string) {
	xpc_stub();
	return -1;
};

XPC_EXPORT
bool _system_version_copy_string_plist(char* out_string) {
	xpc_stub();
	return false;
};

// provided string MUST have at least 48 characters
XPC_EXPORT
bool _system_version_copy_string_sysctl(char* out_string) {
	size_t out_string_length = 48;
	return sysctlbyname("kern.osproductversion", out_string, &out_string_length, NULL, 0) == 0;
};

XPC_EXPORT
bool _system_version_parse_string(const char* string, struct os_system_version* out_version) {
	sscanf(string, "%u.%u.%u", &out_version->major, &out_version->minor, &out_version->patch);
	return true;
};

XPC_EXPORT
int os_system_version_get_current_version(struct os_system_version* out_version) {
	dispatch_once(&current_version_once, ^{
		char version_string[48] = {0};

		if (!_system_version_copy_string_sysctl(version_string)) {
			goto fallback;
		}

		if (!_system_version_parse_string(version_string, &current_version)) {
			goto fallback;
		}

		return;

	fallback:
		memcpy(&current_version, &_system_version_fallback, sizeof(struct os_system_version));
	});

	memcpy(out_version, &current_version, sizeof(struct os_system_version));

	return 0;
};

XPC_EXPORT
int os_system_version_sim_get_current_host_version(uint32_t* out_version) {
	// same as with `os_system_version_get_current_version`
	xpc_stub();
	return -1;
};

XPC_EXPORT
xpc_object_t _xpc_payload_create_from_mach_msg(dispatch_mach_msg_t msg, int some_flag) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
void _xpc_spawnattr_pack_string(char* string_but_with_an_offset_of_AEh, uint32_t* offset, size_t* length, const char* string_to_pack) {
	// `string_to_pack` is copied into `string_but_with_an_offset_of_AEh` after offsetting it by 0xae + `*offset`
	// the length of `string_to_pack` (including the null terminator) is added to `*offset` and subtracted from `*length`
	xpc_stub();
};

XPC_EXPORT
void _xpc_spawnattr_pack_string_fragment(char* string_but_with_an_offset_of_AEh, uint32_t* offset, size_t* length, const char* string_to_pack) {
	// same as `_xpc_spawnattr_pack_string`, but doesn't include the null terminator in the math
	xpc_stub();
};

XPC_EXPORT
const char* _xpc_spawnattr_unpack_string(const char* string, size_t length, uint32_t offset) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
char* _xpc_spawnattr_unpack_strings(char* string_but_with_an_offset_of_AEh, size_t length, uint32_t offset, const char** out_strings, size_t strings_array_size) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t place_hold_on_real_loginwindow(void) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_copy_entitlement_for_self(const char* name) {
    if (!name) return NULL;
    xpc_object_t dictionary=self_signature_entitlement_dictionary();if (!dictionary) return NULL;
    xpc_object_t value=xpc_dictionary_get_value(dictionary,name);
    if (value) xpc_retain(value);
    xpc_release(dictionary);return value;
};

XPC_EXPORT
xpc_object_t xpc_copy_entitlement_for_token(const char* name, audit_token_t* token) {
    if (!name) return NULL;
    xpc_object_t dictionary=peer_signature_entitlement_dictionary(token);if (!dictionary) return NULL;
    xpc_object_t value=xpc_dictionary_get_value(dictionary,name);
    if (value) xpc_retain(value);
    xpc_release(dictionary);return value;
};

XPC_EXPORT
xpc_object_t xpc_copy_entitlements_data_for_token(audit_token_t* token) {
	// returns a data object
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_copy_entitlements_for_pid(pid_t pid) {
	// returns a dictionary
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_copy_entitlements_for_self(void) {
    return self_signature_entitlement_dictionary();
};

XPC_EXPORT
xpc_object_t xpc_copy_bootstrap(void) {
	// returns a dictionary
	xpc_stub();
	return NULL;
};

XPC_EXPORT
char* xpc_copy_code_signing_identity_for_token(audit_token_t* token) {
	// returns a string that must be freed
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_copy_domain(void) {
	// returns a dictionary with a single entry:
	// "pid": <pid of current process>
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_copy_extension_sdk_entry() {
	// not a stub
	// just returns NULL
	// probably has parameters, but there's no way to tell what they are
	xpc_stub();
	return NULL;
};

XPC_EXPORT
const char* xpc_exit_reason_get_label(int reason) {
	// `reason` is actually an enum value
	// this function just maps the values with their names
	xpc_stub();
	return NULL;
};

XPC_EXPORT
void xpc_generate_audit_token(pid_t i_think_this_is_a_pid, audit_token_t* token) {
	xpc_stub();
};

XPC_EXPORT
xpc_endpoint_t xpc_get_attachment_endpoint(void) {
	xpc_stub();
	return NULL;
};

struct some_return_remote_hooks_struct;
struct some_remote_hooks_struct;

XPC_EXPORT
struct some_return_remote_hooks_struct* xpc_install_remote_hooks(struct some_remote_hooks_struct* hooks) {
	// the return struct is different from the input struct
	// it's probably some hooks for the caller to call back into libxpc
	xpc_stub();
	return NULL;
};

XPC_EXPORT
void xpc_set_idle_handler() {
	// not a stub
	// just does nothing
	// probably has parameters, but there's no way to tell what they are
	xpc_stub();
};

XPC_EXPORT
bool xpc_test_symbols_exported() {
	// not a stub
	// just returns false
	// probably has parameters, but there's no way to tell what they are
	xpc_stub();
	return false;
};

XPC_EXPORT
void xpc_track_activity(void) {
	xpc_stub();
};

XPC_EXPORT
int xpc_receive_mach_msg(dispatch_mach_msg_t msg, bool end_transaction, voucher_t voucher, xpc_connection_t connection, xpc_object_t* out_object) {
	// parameter 2's purpose is a guess
	xpc_stub();
	return -1;
};

XPC_EXPORT
int xpc_receive_remote_msg(void* data, size_t data_length, bool some_flag, void* something, xpc_connection_t connection, void (^oolCallback)()) {
	// parameter 4 is unknown
	// parameter 6 seems to be a callback, but i'm not sure if it's a raw function or a block (probably a block)
	// i'm also unsure what the parameters for the callback are
	xpc_stub();
	return -1;
};

XPC_EXPORT
void* xpc_make_serialization(xpc_object_t object, size_t* out_serialization_length) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
void* xpc_make_serialization_with_ool(xpc_object_t object, size_t* out_serialization_length, uint64_t flags) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_create_from_serialization(void* data, size_t data_length) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_create_from_serialization_with_ool(void* data, size_t data_length, void (^oolCallback)()) {
	// same issue with `oolCallback` as in `xpc_receive_remote_msg`
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_create_reply_with_format_and_arguments(xpc_object_t original, const char* format, va_list args) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_create_reply_with_format(xpc_object_t original, const char* format, ...) {
	va_list args;
	va_start(args, format);
	xpc_object_t result = xpc_create_reply_with_format_and_arguments(original, format, args);
	va_end(args);
	return result;
};

XPC_EXPORT
xpc_object_t xpc_create_with_format_and_arguments(const char* format, va_list args) {
	xpc_stub();
	return NULL;
};

XPC_EXPORT
xpc_object_t xpc_create_with_format(const char* format, ...) {
	va_list args;
	va_start(args, format);
	xpc_object_t result = xpc_create_with_format_and_arguments(format, args);
	va_end(args);
	return result;
};
