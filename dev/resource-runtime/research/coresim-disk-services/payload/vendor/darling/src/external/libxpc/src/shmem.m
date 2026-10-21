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

#import <xpc/objects/shmem.h>
#import <xpc/util.h>
#import <xpc/xpc.h>
#import <xpc/serialization.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach/memory_object_types.h>
#include <malloc/malloc.h>
#include <unistd.h>

XPC_CLASS_SYMBOL_DECL(shmem);

OS_OBJECT_NONLAZY_CLASS
@implementation XPC_CLASS(shmem)

XPC_CLASS_HEADER(shmem);

- (instancetype)initWithOwnedPort: (mach_port_t)port length: (size_t)length
{
	if (self = [super init]) {
		XPC_THIS_DECL(shmem);
		this->port = port;
		this->length = length;
		if (!MACH_PORT_VALID(port) || !length) {
			[self release];
			return nil;
		}
	}
	return self;
}

- (void)dealloc
{
	XPC_THIS_DECL(shmem);
	xpc_mach_port_release_send(this->port);
	[super dealloc];
}

- (mach_port_t)port { return XPC_THIS(shmem)->port; }
- (size_t)length { return XPC_THIS(shmem)->length; }

- (size_t)mapRegion: (void**)region
{
	XPC_THIS_DECL(shmem);
	if (!region) return 0;
	mach_vm_address_t address = 0;
	// IS_MASK requests the protections permitted by the capability. This
	// preserves read-only entries, including those received over IPC.
	vm_prot_t protection = VM_PROT_READ | VM_PROT_WRITE | VM_PROT_IS_MASK;
	kern_return_t result = mach_vm_map(mach_task_self(), &address, this->length,
		0, VM_FLAGS_ANYWHERE, this->port, 0, FALSE,
		protection, protection, VM_INHERIT_NONE);
	if (result != KERN_SUCCESS) return 0;
	*region = (void*)address;
	return this->length;
}

- (instancetype)copy
{
	XPC_THIS_DECL(shmem);
	if (xpc_mach_port_retain_send(this->port) != KERN_SUCCESS) return nil;
	return [[XPC_CLASS(shmem) alloc] initWithOwnedPort: this->port length: this->length];
}

- (BOOL)isEqual: (id)object { return self == object; }
- (NSUInteger)hash { return XPC_THIS(shmem)->port; }

- (char*)xpcDescription
{
	XPC_THIS_DECL(shmem);
	char* result = NULL;
	asprintf(&result, "<%s: port = %u, length = %zu>",
		xpc_class_name(self), this->port, this->length);
	return result;
}

@end

@implementation XPC_CLASS(shmem) (XPCSerialization)

- (BOOL)serializable { return YES; }
- (NSUInteger)serializationLength
{
	return xpc_serial_padded_length(sizeof(xpc_serial_type_t))
		+ xpc_serial_padded_length(sizeof(uint64_t));
}

- (BOOL)serialize: (XPC_CLASS(serializer)*)serializer
{
	XPC_THIS_DECL(shmem);
	return [serializer writeU32: XPC_SERIAL_TYPE_SHMEM]
		&& [serializer writeU64: this->length]
		&& [serializer writePort: this->port type: MACH_MSG_TYPE_COPY_SEND];
}

+ (instancetype)deserialize: (XPC_CLASS(deserializer)*)deserializer
{
	uint32_t type = XPC_SERIAL_TYPE_INVALID;
	uint64_t length = 0;
	mach_port_t port = MACH_PORT_NULL;
	if (![deserializer readU32: &type] || type != XPC_SERIAL_TYPE_SHMEM
		|| ![deserializer readU64: &length]
		|| ![deserializer readPort: &port type: MACH_MSG_TYPE_PORT_SEND]) return nil;
	// readPort transfers the received reference to us. Reject malformed
	// lengths without leaking that reference or allowing arithmetic wrap.
	size_t page = (size_t)getpagesize();
	if (!length || length > INT64_MAX || (length & (page - 1))) {
		xpc_mach_port_release_send(port);
		return nil;
	}
	return [[self alloc] initWithOwnedPort: port length: (size_t)length];
}

@end

//
// C API
//

static xpc_object_t xpc_shmem_create_with_protection(const void* region, size_t length, vm_prot_t protection) {
	if (!region || !length || length > INT64_MAX) return NULL;
	if (malloc_size(region)) xpc_abort("xpc_shmem_create cannot share a malloc allocation");
	memory_object_size_t size = length;
	mach_port_t port = MACH_PORT_NULL;
	kern_return_t result = mach_make_memory_entry_64(mach_task_self(), &size,
		(memory_object_offset_t)region, protection | VM_PROT_IS_MASK | MAP_MEM_VM_SHARE,
		&port, MACH_PORT_NULL);
	if (result == KERN_INVALID_VALUE) {
		size = length;
		result = mach_make_memory_entry_64(mach_task_self(), &size,
			(memory_object_offset_t)region, protection | VM_PROT_IS_MASK, &port, MACH_PORT_NULL);
	}
	if (result != KERN_SUCCESS) return NULL;
	if (size < length) {
		xpc_mach_port_release_send(port);
		return NULL;
	}
	return [[XPC_CLASS(shmem) alloc] initWithOwnedPort: port length: (size_t)size];
};

XPC_EXPORT
xpc_object_t xpc_shmem_create(void* region, size_t length) {
	return xpc_shmem_create_with_protection(region, length, VM_PROT_READ | VM_PROT_WRITE);
};

XPC_EXPORT
size_t xpc_shmem_map(xpc_object_t xshmem, void** region) {
	TO_OBJC_CHECKED(shmem, xshmem, shmem) {
		return [shmem mapRegion: region];
	}
	return 0;
};

//
// private C API
//

XPC_EXPORT
mach_port_t _xpc_shmem_get_mach_port(xpc_object_t xshmem) {
	TO_OBJC_CHECKED(shmem, xshmem, shmem) {
		return shmem.port;
	}
	return MACH_PORT_NULL;
};

XPC_EXPORT
xpc_object_t xpc_shmem_create_readonly(const void* region, size_t length) {
	return xpc_shmem_create_with_protection(region, length, VM_PROT_READ);
};

XPC_EXPORT
size_t xpc_shmem_get_length(xpc_object_t xshmem) {
	TO_OBJC_CHECKED(shmem, xshmem, shmem) {
		return shmem.length;
	}
	return 0;
};
