
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>
#include <unistd.h>
#include <sys/syscall.h>
#define LINUX_SYSCALL(n,...) syscall(n, ##__VA_ARGS__)
#define kern_printf(...) fprintf(stderr,__VA_ARGS__)
#define __simple_snprintf snprintf
struct _darling_libkernel_callbacks { int (*dyld_func_lookup)(const char*,void**); } _darling_libkernel_callbacks;
_Static_assert(sizeof(void*)==sizeof(_darling_libkernel_callbacks.dyld_func_lookup),"lookup pointer ABI");
/* Best-effort current-process metadata, not a loader-lifetime guarantee. No
 * allocation, symbol search, dyld lock, Mach/server RPC, or other-process read.
 * The lock-free range reader does not pin an ImageLoader against dlclose. */
static int copy_signal_path(char* destination, unsigned capacity, const char* source)
{
	unsigned i = 0;
	while (i < capacity - 1 && source[i]) {
		unsigned char byte = (unsigned char)source[i];
		destination[i] = (byte < 32 || byte == 127) ? '?' : (char)byte;
		++i;
	}
	destination[i] = 0;
	return source[i] != 0;
}

static void log_signal_identity(int signal_number, unsigned long long pc)
{
	/* These are Linux syscall values in the current PID namespace. Do not
	 * claim they are server-host or separately translated Darwin process IDs. */
	long pid = LINUX_SYSCALL(__NR_getpid);
	long tid = LINUX_SYSCALL(__NR_gettid);
	/* Retain identity even if the interrupted event involves dyld metadata. */
	kern_printf("sigexc: signal-event phase=identity linux_pid=%ld linux_tid=%ld signal=%d pc=0x%llx\n",
		pid, tid, signal_number, pc);
	static int resolving;
	const char* lookup = "uninitialized";
	const char* executable_status = "uninitialized";
	const char* image = "<unknown>";
	const char* executable = "<unknown>";
	unsigned long long header_address = 0, offset = 0;
	char path[512], main_path[512], record[1536];
	int truncated = 0;

	/* Nonblocking guard: another/nested signal event still gets identity. */
	if (__atomic_exchange_n(&resolving, 1, __ATOMIC_ACQUIRE)) {
		lookup = executable_status = "busy";
	} else {
		if (_darling_libkernel_callbacks.dyld_func_lookup) {
			const char* (*image_path)(const void*) = NULL;
			const void* (*image_header)(const void*) = NULL;
			int (*executable_path)(char*, uint32_t*) = NULL;
			_darling_libkernel_callbacks.dyld_func_lookup(
				"__dyld_image_path_containing_address", (void**)&image_path);
			_darling_libkernel_callbacks.dyld_func_lookup(
				"__dyld_get_image_header_containing_address", (void**)&image_header);
			_darling_libkernel_callbacks.dyld_func_lookup(
				"__dyld__NSGetExecutablePath", (void**)&executable_path);
			executable_status = "unavailable";
			if (executable_path) {
				uint32_t capacity = sizeof(main_path);
				main_path[0] = main_path[sizeof(main_path) - 1] = 0;
				/* dyld's stable startup executable path; unlike image-index
				 * lookup this does not read a reallocating image-info vector. */
				if (executable_path(main_path, &capacity) == 0) {
					for (unsigned i = 0; i < sizeof(main_path) - 1 && main_path[i]; ++i)
						if ((unsigned char)main_path[i] < 32 || main_path[i] == 127)
							main_path[i] = '?';
					executable = main_path;
					executable_status = "resolved";
				} else {
					executable_status = "too-long";
				}
			}
			/* The main path was copied from stable startup storage. Emit it
			 * before attempting the borrowed, best-effort image lookup. */
			int main_length = __simple_snprintf(record, sizeof(record),
				"sigexc: signal-event phase=executable linux_pid=%ld linux_tid=%ld signal=%d pc=0x%llx executable_status=%s executable=%s\n",
				pid, tid, signal_number, pc, executable_status, executable);
			if (main_length > 0 && main_length < sizeof(record))
				LINUX_SYSCALL(__NR_write, 2, record, main_length);
			lookup = "unavailable";
			if (image_path && image_header) {
				/* Darling dyld's existing mapped-range reader is lock-free. */
				const void* address = (const void*)(uintptr_t)pc;
				const char* name = image_path(address);
				const void* header = image_header(address);
				lookup = "unknown";
				if (name && header && (uintptr_t)header <= pc) {
					truncated = copy_signal_path(path, sizeof(path), name);
					image = path;
					header_address = (uintptr_t)header;
					offset = pc - header_address;
					lookup = "resolved";
				}
			}
		}
		__atomic_store_n(&resolving, 0, __ATOMIC_RELEASE);
	}
	/* __simple_fprintf uses a 512-byte internal buffer. Format the bounded
	 * pair of paths here and perform one direct Linux write instead. */
	int length = __simple_snprintf(record, sizeof(record),
		"sigexc: signal-event phase=image metadata=best-effort linux_pid=%ld linux_tid=%ld signal=%d pc=0x%llx header=0x%llx offset=0x%llx lookup=%s executable_status=%s image_truncated=%d executable=%s image=%s\n",
		pid, tid, signal_number, pc, header_address, offset, lookup, executable_status,
		truncated, executable, image);
	if (length < 0) return;
	if (length >= sizeof(record)) {
		length = sizeof(record) - 1;
		record[length - 1] = '\n';
	}
	LINUX_SYSCALL(__NR_write, 2, record, length);
}
static int mode, nested;
static char long_image[1100];
static const char *get_path(const void* address) {
 (void)address;
 if(mode==4)return 0;
 if(mode==7)return long_image;
 if(mode==8)return "/test/line\nname\timage";
 return "/test/owned-image.dylib";
}
static const void *get_header(const void* address) {
 (void)address;return mode==5?0:(const void*)(uintptr_t)(mode==6?0x2000:0x1000);
}
static int get_executable(char* buffer,uint32_t* capacity) {
 if(mode==9){*capacity=800;return -1;}
 const char*name="/test/owned-process";size_t n=strlen(name)+1;
 if(*capacity<n){*capacity=n;return -1;}memcpy(buffer,name,n);return 0;
}
static int lookup(const char*name,void**value) {
 *value=0;
 if(mode==1)return 0;
 if(mode==10&&!nested){nested=1;log_signal_identity(11,0x1200);}
 if(!strcmp(name,"__dyld_image_path_containing_address"))*value=(void*)get_path;
 else if(!strcmp(name,"__dyld_get_image_header_containing_address")&&mode!=2)*value=(void*)get_header;
 else if(!strcmp(name,"__dyld__NSGetExecutablePath"))*value=(void*)get_executable;
 return *value!=0;
}
int main(void) {
 memset(long_image,'A',sizeof(long_image)-1);
 for(mode=0;mode<=10;mode++) {
  fprintf(stderr,"HOSTCASE mode=%d\n",mode);
  _darling_libkernel_callbacks.dyld_func_lookup=mode?lookup:0;
  log_signal_identity(11,0x1200);
 }
 return 0;
}
