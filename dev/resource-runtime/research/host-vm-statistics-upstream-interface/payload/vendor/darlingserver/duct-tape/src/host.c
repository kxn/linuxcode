#include <darlingserver/duct-tape/stubs.h>
#include <darlingserver/duct-tape/processor.h>

#include <kern/host.h>
#include <mach_debug/mach_debug.h>

#include <libsimple/lock.h>

// Linux sysinfo (from the sysinfo man page)
struct sysinfo {
	long uptime;
	unsigned long loads[3];
	unsigned long totalram;
	unsigned long freeram;
	unsigned long sharedram;
	unsigned long bufferram;
	unsigned long totalswap;
	unsigned long freeswap;
	unsigned short procs;
	unsigned long totalhigh;
	unsigned long freehigh;
	unsigned int mem_unit;
	char _f[20 - 2 * sizeof(long) - sizeof(int)];
};
int sysinfo(struct sysinfo *info);

// Linux sysconf
long sysconf(int name);
#define _SC_NPROCESSORS_CONF 83
#define _SC_NPROCESSORS_ONLN 84

// Native Linux libc, as in memory.c. Do not include Linux headers alongside XNU.
int open(const char* path, int flags, ...);
long read(int fd, void* buffer, unsigned long size);
int close(int fd);
int* __errno_location(void);
#define LINUX_O_CLOEXEC 0x80000
#define LINUX_EINTR 4

static bool meminfo_pages(const char* text, const char* key, natural_t* pages) {
	size_t length = strlen(key);
	for (const char* line = text; line && *line; line = strchr(line, '\n')) {
		if (*line == '\n') ++line;
		if (strncmp(line, key, length) || line[length] != ':') continue;
		const char* value = line + length + 1;
		while (*value == ' ' || *value == '\t') ++value;
		if (*value < '0' || *value > '9') return false;
		uint64_t kib = 0;
		do {
			unsigned digit = *value++ - '0';
			if (kib > (UINT64_MAX - digit) / 10) return false;
			kib = kib * 10 + digit;
		} while (*value >= '0' && *value <= '9');
		while (*value == ' ' || *value == '\t') ++value;
		if (strncmp(value, "kB", 2)) return false;
		value += 2;
		while (*value == ' ' || *value == '\t') ++value;
		if ((*value && *value != '\n') || kib > UINT64_MAX / 1024) return false;
		*pages = VM_STATISTICS_TRUNCATE_TO_32_BIT(kib * 1024 / PAGE_SIZE);
		return true;
	}
	return false;
}

static kern_return_t linux_vm_stats(vm_statistics64_t stat) {
	char text[16384];
	unsigned long used = 0;
	int fd = open("/proc/meminfo", LINUX_O_CLOEXEC);
	if (fd < 0) return KERN_FAILURE;
	for (;;) {
		long size = read(fd, text + used, sizeof(text) - 1 - used);
		if (size < 0 && *__errno_location() == LINUX_EINTR) continue;
		if (size <= 0) {
			close(fd);
			if (size < 0) return KERN_FAILURE;
			break;
		}
		used += size;
		if (used == sizeof(text) - 1) {
			close(fd);
			return KERN_FAILURE; // Do not silently accept a truncated snapshot.
		}
	}
	text[used] = '\0';
	memset(stat, 0, sizeof(*stat));
	// Translate measured Linux page states, not MemAvailable or Committed_AS.
	// Unevictable is the userspace subset of wired memory; Linux has no exact
	// Darwin wired/compressor/purgeable/event-counter equivalent. Those other
	// counters remain unavailable (zero), rather than inventing measurements.
	if (!meminfo_pages(text, "MemFree", &stat->free_count) ||
	    !meminfo_pages(text, "Active", &stat->active_count) ||
	    !meminfo_pages(text, "Inactive", &stat->inactive_count) ||
	    !meminfo_pages(text, "Unevictable", &stat->wire_count)) return KERN_FAILURE;
	return KERN_SUCCESS;
}

static void cache_sysinfo(void* context) {
	struct sysinfo* cached_sysinfo = context;

	if (sysinfo(cached_sysinfo) < 0) {
		panic("Failed to retrieve sysinfo");
	}
};

kern_return_t host_info(host_t host, host_flavor_t flavor, host_info_t info, mach_msg_type_number_t* count) {
	static libsimple_once_t once_token = LIBSIMPLE_ONCE_INITIALIZER;
	static struct sysinfo cached_sysinfo;

	if (host == HOST_NULL) {
		return KERN_INVALID_ARGUMENT;
	}

	switch (flavor) {
		case HOST_BASIC_INFO: {
			host_basic_info_t basic_info = (host_basic_info_t)info;

			// need at least enough space for the legacy structure
			if (*count < HOST_BASIC_INFO_OLD_COUNT) {
				return KERN_FAILURE;
			}

			libsimple_once(&once_token, cache_sysinfo, &cached_sysinfo);

			uint64_t memsize = cached_sysinfo.totalram * cached_sysinfo.mem_unit;

			basic_info->memory_size = memsize;
#if __x86_64__ || __i386__
			basic_info->cpu_type = CPU_TYPE_X86;
#if __x86_64__
			basic_info->cpu_subtype = dtape_processor_cpu_subtype();
#else
			basic_info->cpu_subtype = CPU_SUBTYPE_I386_ALL;
#endif
#else
			#error Unknown CPU type
#endif
			basic_info->max_cpus = sysconf(_SC_NPROCESSORS_CONF);
			basic_info->avail_cpus = sysconf(_SC_NPROCESSORS_ONLN);

			// if there's room for the modern structure, fill in some additional info
			if (*count >= HOST_BASIC_INFO_COUNT) {
				// TODO: properly differentiate physical vs. logical cores
				dtape_stub_safe("modern HOST_BASIC_INFO");
				basic_info->cpu_threadtype = CPU_THREADTYPE_NONE;
				basic_info->physical_cpu = basic_info->avail_cpus;
				basic_info->physical_cpu_max = basic_info->max_cpus;
				basic_info->logical_cpu = basic_info->avail_cpus;
				basic_info->logical_cpu_max = basic_info->max_cpus;

				basic_info->max_mem = memsize;

				*count = HOST_BASIC_INFO_COUNT;
			} else {
				*count = HOST_BASIC_INFO_OLD_COUNT;
			}

			return KERN_SUCCESS;
		}

		case HOST_PRIORITY_INFO: {
			// <copied from="xnu://7195.141.2/osfmk/kern/host.c">
			host_priority_info_t priority_info;

			if (*count < HOST_PRIORITY_INFO_COUNT) {
				return KERN_FAILURE;
			}

			priority_info = (host_priority_info_t)info;

			priority_info->kernel_priority = MINPRI_KERNEL;
			priority_info->system_priority = MINPRI_KERNEL;
			priority_info->server_priority = MINPRI_RESERVED;
			priority_info->user_priority = BASEPRI_DEFAULT;
			priority_info->depress_priority = DEPRESSPRI;
			priority_info->idle_priority = IDLEPRI;
			priority_info->minimum_priority = MINPRI_USER;
			priority_info->maximum_priority = MAXPRI_RESERVED;

			*count = HOST_PRIORITY_INFO_COUNT;

			return KERN_SUCCESS;
			// </copied>
		}

		case HOST_DEBUG_INFO_INTERNAL:
			return KERN_NOT_SUPPORTED;

		case HOST_PREFERRED_USER_ARCH: {
			host_preferred_user_arch_t user_arch_info;

			if (*count < HOST_PREFERRED_USER_ARCH_COUNT) {
				return KERN_FAILURE;
			}

			*count = HOST_PREFERRED_USER_ARCH_COUNT;

			user_arch_info = (void*)info;

#if __x86_64__ || __i386__
			user_arch_info->cpu_type = CPU_TYPE_X86;
#if __x86_64__
			user_arch_info->cpu_subtype = dtape_processor_cpu_subtype();
#else
			user_arch_info->cpu_subtype = CPU_SUBTYPE_I386_ALL;
#endif
#elif __aarch64__
			// TODO: check whether this is actually what ARM64 macOS returns
			user_arch_info->cpu_type = CPU_TYPE_ARM64;
			user_arch_info->cpu_subtype = CPU_SUBTYPE_ARM64_ALL;
#else
			#error HOST_PREFERRED_USER_ARCH not implemented for this architecture
#endif

			return KERN_SUCCESS;
		};

		case HOST_SCHED_INFO:
			dtape_stub_unsafe("HOST_SCHED_INFO");
		case HOST_RESOURCE_SIZES:
			dtape_stub_unsafe("HOST_RESOURCE_SIZES");
		case HOST_CAN_HAS_DEBUGGER:
			dtape_stub_unsafe("HOST_CAN_HAS_DEBUGGER");
		case HOST_VM_PURGABLE:
			dtape_stub_unsafe("HOST_VM_PURGABLE");

		case HOST_MACH_MSG_TRAP:
		case HOST_SEMAPHORE_TRAPS:
			*count = 0;
			return KERN_SUCCESS;

		default:
			return KERN_INVALID_ARGUMENT;
	}
};

kern_return_t host_default_memory_manager(host_priv_t host_priv, memory_object_default_t* default_manager, memory_object_cluster_size_t cluster_size) {
	dtape_stub_unsafe();
};

kern_return_t host_get_boot_info(host_priv_t host_priv, kernel_boot_info_t boot_info) {
	dtape_stub_unsafe();
};

kern_return_t host_get_UNDServer(host_priv_t host_priv, UNDServerRef* serverp) {
	dtape_stub_unsafe();
};

kern_return_t host_set_UNDServer(host_priv_t host_priv, UNDServerRef server) {
	dtape_stub_unsafe();
};

kern_return_t host_lockgroup_info(host_t host, lockgroup_info_array_t* lockgroup_infop, mach_msg_type_number_t* lockgroup_infoCntp) {
	dtape_stub_unsafe();
};

kern_return_t host_reboot(host_priv_t host_priv, int options) {
	dtape_stub_unsafe();
};

kern_return_t host_security_create_task_token(host_security_t host_security, task_t parent_task, security_token_t sec_token, audit_token_t audit_token, host_priv_t host_priv, ledger_port_array_t ledger_ports, mach_msg_type_number_t num_ledger_ports, boolean_t inherit_memory, task_t* child_task) {
	dtape_stub_safe();
	return KERN_NOT_SUPPORTED;
};

kern_return_t host_security_set_task_token(host_security_t host_security, task_t task, security_token_t sec_token, audit_token_t audit_token, host_priv_t host_priv) {
	dtape_stub_unsafe();
};

kern_return_t host_virtual_physical_table_info(host_t host, hash_info_bucket_array_t* infop, mach_msg_type_number_t* countp) {
	dtape_stub_unsafe();
};

kern_return_t host_statistics(host_t host, host_flavor_t flavor, host_info_t info, mach_msg_type_number_t* count) {
	if (host == HOST_NULL) return KERN_INVALID_HOST;
	switch (flavor) {
		case HOST_VM_INFO: {
			if (*count < HOST_VM_INFO_REV0_COUNT) return KERN_FAILURE;
			vm_statistics64_data_t measured;
			kern_return_t result = linux_vm_stats(&measured);
			if (result != KERN_SUCCESS) return result;
			vm_statistics_data_t stat = {0};
			stat.free_count = measured.free_count;
			stat.active_count = measured.active_count;
			stat.inactive_count = measured.inactive_count;
			stat.wire_count = measured.wire_count;
			// Match the revision/count negotiation in paired XNU kern/host.c.
			*count = *count >= HOST_VM_INFO_REV2_COUNT ? HOST_VM_INFO_REV2_COUNT :
			         *count >= HOST_VM_INFO_REV1_COUNT ? HOST_VM_INFO_REV1_COUNT : HOST_VM_INFO_REV0_COUNT;
			memcpy(info, &stat, *count * sizeof(integer_t));
			return KERN_SUCCESS;
		}

		case HOST_CPU_LOAD_INFO:
			dtape_stub_safe("HOST_CPU_LOAD_INFO");
			return KERN_INVALID_ARGUMENT;

		default:
			dtape_stub_unsafe();
	}
};

kern_return_t vm_stats(void* info, unsigned int* count) {
	if (*count < HOST_VM_INFO64_REV0_COUNT) return KERN_FAILURE;
	vm_statistics64_data_t stat;
	kern_return_t result = linux_vm_stats(&stat);
	if (result != KERN_SUCCESS) return result;
	// Keep XNU's historical revision support and write only the returned count.
	*count = *count >= HOST_VM_INFO64_REV1_COUNT ? HOST_VM_INFO64_REV1_COUNT : HOST_VM_INFO64_REV0_COUNT;
	memcpy(info, &stat, *count * sizeof(integer_t));
	return KERN_SUCCESS;
};
