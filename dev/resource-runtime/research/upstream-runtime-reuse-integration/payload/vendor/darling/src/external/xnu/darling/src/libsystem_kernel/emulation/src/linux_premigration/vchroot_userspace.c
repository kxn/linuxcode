#include <darling-config.h>

#include <darling/emulation/linux_premigration/vchroot_expand.h>
#ifdef TEST
#	include <unistd.h>
#	include <sys/stat.h>
#	include <sys/syscall.h>
#	include <stdio.h>
#	include <stdbool.h>
#	include <stdlib.h>
#	include <string.h>
#	include <errno.h>
#	include <dirent.h>
#	include <fcntl.h>

#	define LINUX_SYSCALL(...) ({ int __rv = syscall(__VA_ARGS__); if (__rv == -1) __rv = -errno; __rv; })
#	define LINUX_ENOENT ENOENT
#	define LINUX_ELOOP ELOOP
#	define LINUX_ENAMETOOLONG ENAMETOOLONG
#   define LINUX_EFAULT EFAULT

#	define LINUX_S_IFMT S_IFMT
#	define LINUX_S_IFLNK S_IFLNK

#	define LINUX_O_RDONLY O_RDONLY

#	define __simple_sprintf sprintf
#	define linux_dirent64 dirent
typedef struct stat stat_t;
#else
#	include <stdbool.h>
#   include <stddef.h>

#	include <darling/emulation/xnu_syscall/bsd/impl/fcntl/open.h>
#	include <darling/emulation/common/base.h>
#	include <darling/emulation/other/mach/lkm.h>
#	include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#	include <darling/emulation/common/simple.h>
#	include <darling/emulation/conversion/dirent/getdirentries.h>
#	include <darling/emulation/conversion/errno.h>
#	include <darling/emulation/conversion/fcntl/open.h>
#	include <darling/emulation/conversion/duct_errno.h>
#	include <darling/emulation/conversion/stat/common.h>
#	include <darling/emulation/xnu_syscall/bsd/impl/dirent/getdirentries.h>
#	include <darling/emulation/conversion/common_at.h>

#include <darlingserver/rpc.h>

typedef struct linux_stat stat_t;

struct _xlocale;
typedef struct _xlocale* locale_t;

#define LC_C_LOCALE ((locale_t)NULL)

extern __SIZE_TYPE__ strlen(const char* s);
extern char* strcpy(char* dest, const char* src);
extern int strcmp(const char* str1, const char* str2);
extern int strncmp(const char* str1, const char* str2, __SIZE_TYPE__ n);
extern int strncasecmp_l(const char* str1, const char* str2, __SIZE_TYPE__ n, locale_t locale);
extern int strcasecmp(const char* str1, const char* str2);
extern char* strcat(char* dest, const char* src);
extern char *strchr(const char *s, int c);
extern void *memcpy(void *dest, const void *src, __SIZE_TYPE__ n);
extern void* memmove(void* dest, const void* src, __SIZE_TYPE__ n);
extern int memcmp(const void* dest, const void* src, __SIZE_TYPE__ n);

#define LINUX_S_IFMT 00170000
#define LINUX_S_IFLNK 0120000

#define __simple_printf(...)
// #define __simple_printf __simple_kprintf // For bug hunting

#endif

// Embed only the reachable allocation-free normalization implementation. All
// utf8proc symbols have internal linkage; no new libsystem exports or heap calls.
#define UTF8PROC_STATIC
#define UTF8PROC_DLLEXPORT static
#define DARLING_UTF8PROC_PRIVATE
#include "utf8proc/utf8proc.c"
#undef UTF8PROC_DLLEXPORT
#undef DARLING_UTF8PROC_PRIVATE

static bool next_component(const char* from, const char** end);

static char prefix_path[4096] = {0}; // MUST NOT end with '/'
static int prefix_path_len = -1;

static const char EXIT_PATH[] = "/Volumes/SystemRoot";

#ifndef TEST
#define icase_enabled true
#else
static bool icase_enabled = true;
#endif

static bool vchroot_component_icase_equal(const char* left, const char* right)
{
#ifdef VARIANT_DYLD
    // dyld runs before libc/pthread locale initialization. Reuse the normal
    // component fallback without strcasecmp's __current_locale/TSD access.
    // Fold only ASCII: non-ASCII bytes retain the existing normalization path.
    unsigned char a, b;
    do {
        a = (unsigned char)*left++;
        b = (unsigned char)*right++;
        if (a >= 'A' && a <= 'Z') a += 'a' - 'A';
        if (b >= 'A' && b <= 'Z') b += 'a' - 'A';
        if (a != b) return false;
    } while (a);
    return true;
#else
    return strcasecmp(left, right) == 0;
#endif
}

// XNU bsd/sys/param.h: MAXSYMLINKS is cumulative over one pathname lookup.
static const int VCHROOT_MAX_SYMLINKS = 32;

struct context
{
	const char* current_root;
	int current_root_len;

	char current_path[4096];
	int current_path_len;

	int symlinks_followed;
	char dirents[4096];
	bool unknown_component;
	bool follow;
};

static int vchroot_run(const char* path, struct context* ctxt);

// Exact Linux lookups always take precedence. On a miss, resolve canonical
// Unicode spellings (NFD), retaining the existing ASCII case-insensitive match.
// Buffers are bounded and the helper is not inlined into symlink recursion.
// A Linux directory entry is at most 255 bytes; 1024 scalar slots also cover
// its maximum canonical decomposition. Invalid UTF-8 remains byte-oriented.
static __attribute__((noinline)) int vchroot_matching_component(struct context* ctxt, int offset)
{
    utf8proc_int32_t wanted[1024], candidate[1024];
    const char* component = ctxt->current_path + offset;
    const unsigned options = UTF8PROC_STABLE | UTF8PROC_DECOMPOSE;
    utf8proc_ssize_t wanted_len = utf8proc_decompose((const utf8proc_uint8_t*)component,
        strlen(component), wanted, 1024, options);
    bool normalize = wanted_len > 0 && wanted_len <= 1024;
    if (!icase_enabled && !normalize) return 0;

    ctxt->current_path[offset - 1] = 0;
#if defined(__NR_open)
    int dfd = LINUX_SYSCALL(__NR_open, offset > 1 ? ctxt->current_path : "/", LINUX_O_RDONLY);
#else
    int dfd = LINUX_SYSCALL(__NR_openat, LINUX_AT_FDCWD, offset > 1 ? ctxt->current_path : "/", LINUX_O_RDONLY);
#endif
    ctxt->current_path[offset - 1] = '/';
    if (dfd < 0) return 0;
    char selected[256];
    int matches = 0, received;
    while ((received = LINUX_SYSCALL(__NR_getdents64, dfd, ctxt->dirents, sizeof(ctxt->dirents))) > 0) {
        for (int pos = 0; pos < received;) {
            struct linux_dirent64* de = (struct linux_dirent64*)&ctxt->dirents[pos];
            // The kernel supplies these records, but never walk a partial one.
            if (de->d_reclen <= offsetof(struct linux_dirent64, d_name) || pos + de->d_reclen > received) {
                matches = -1;
                goto finished;
            }
            bool equal = icase_enabled && vchroot_component_icase_equal(de->d_name, component);
            if (!equal && normalize) {
                utf8proc_ssize_t count = utf8proc_decompose((const utf8proc_uint8_t*)de->d_name,
                    strlen(de->d_name), candidate, 1024, options);
                equal = count == wanted_len && count > 0 && count <= 1024
                    && memcmp(wanted, candidate, count * sizeof(*wanted)) == 0;
            }
            if (equal) {
                // Linux permits canonical aliases. Never pick an arbitrary file
                // if a non-exact request can name more than one directory entry.
                if (++matches > 1) goto finished;
                strcpy(selected, de->d_name);
            }
            pos += de->d_reclen;
        }
    }
    if (received < 0) matches = -1;
finished:
    LINUX_SYSCALL(__NR_close, dfd);
    if (matches > 1 || matches < 0) return -LINUX_ENOENT;
    if (matches == 0) return 0;
    size_t length = strlen(selected);
    if (offset + length + 1 > sizeof(ctxt->current_path)) return -LINUX_ENAMETOOLONG;
    memcpy(ctxt->current_path + offset, selected, length + 1);
    ctxt->current_path_len = offset + length;
    return 1;
}


int vchroot_copy_path(struct vchroot_expand_args* args,const char* path)
{
    if(!args||!path)return -LINUX_EFAULT;
    // Darwin PATH_MAX includes the terminator. Read within a single Linux
    // page at a time, so a valid NUL at a guard-page boundary is not rejected.
    unsigned copied=0;
    while(copied<1024){
        char bytes[256];unsigned count=sizeof bytes;
        if(count>1024-copied)count=1024-copied;
        unsigned until_page=4096-(((unsigned long)path+copied)&4095);
        if(count>until_page)count=until_page;
#ifdef TEST
        memcpy(bytes,path+copied,count);long received=count;
#else
        struct {void* base;__SIZE_TYPE__ length;} local={bytes,count},remote={(void*)(path+copied),count};
        long pid=LINUX_SYSCALL(__NR_getpid);
        long received=LINUX_SYSCALL(__NR_process_vm_readv,pid,&local,1,&remote,1,0);
#endif
        if(received<=0)return -LINUX_EFAULT;
        for(unsigned i=0;i<(unsigned)received;i++){
            args->path[copied+i]=bytes[i];
            if(!bytes[i])return 0;
        }
        copied+=received;
    }
    return -LINUX_ENAMETOOLONG;
}

#ifndef TEST
VISIBLE
#endif
int __darling_vchroot(int dfd)
{
	int rv;

#ifndef TEST
	rv = errno_linux_to_bsd(dserver_rpc_vchroot(dfd));
	if (rv != 0)
		return rv;
#endif

	char buf[50];

	__simple_sprintf(buf, "/proc/self/fd/%d", dfd);

	#if defined(__NR_readlink)
		rv = LINUX_SYSCALL(__NR_readlink, buf, prefix_path, sizeof(prefix_path) - 1);
	#else
		rv = LINUX_SYSCALL(__NR_readlinkat, LINUX_AT_FDCWD, buf, prefix_path, sizeof(prefix_path) - 1);
	#endif
	prefix_path[rv] = '\0';
	prefix_path_len = rv;

	return 0;
}

#ifndef TEST
VISIBLE
int __darling_vchroot_expand(const char* path, char* out)
{
	struct vchroot_expand_args a = {
		.dfd = -100,
		.flags = 0
	};

	if(!out)return -LINUX_EFAULT;
	int rv=vchroot_copy_path(&a,path);
	if(rv<0)return rv;
	rv = vchroot_expand(&a);
	if(rv==0)strcpy(out, a.path);
	return rv;
}
#endif

static void init_vchroot_path(void)
{
	uint64_t tmp_len;
	int code = dserver_rpc_vchroot_path(prefix_path, sizeof(prefix_path), &tmp_len);
	if (code < 0) {
		__simple_printf("Failed to get vchroot path: %d\n", code);
		__simple_abort();
	}

	prefix_path_len = (int)tmp_len;

#ifndef TEST
	__simple_printf("init_vchroot_path: %s\n", prefix_path);
#endif
}

int vchroot_expand(struct vchroot_expand_args* args)
{
	struct context ctxt;

#ifndef TEST
	if (prefix_path_len == -1)
		init_vchroot_path();
	__simple_printf("vchroot_expand(): input %s\n", args->path);
#endif

	ctxt.unknown_component = false;
	ctxt.symlinks_followed = 0;
	ctxt.current_root = prefix_path;
	ctxt.current_root_len = prefix_path_len;
	ctxt.follow = !!(args->flags & VCHROOT_FOLLOW);

	const char* input_path = args->path;

	if (*input_path == '\0')
		return -LINUX_ENOENT;

	if (*input_path != '/')
	{
		char buf[50];

		if (args->dfd != -100)
			__simple_sprintf(buf, "/proc/self/fd/%d", args->dfd);
		else
			strcpy(buf, "/proc/self/cwd");

		#if defined(__NR_readlink)
			int rv = LINUX_SYSCALL(__NR_readlink, buf, ctxt.current_path, sizeof(ctxt.current_path) - 1);
		#else
			int rv = LINUX_SYSCALL(__NR_readlinkat, LINUX_AT_FDCWD, buf, ctxt.current_path, sizeof(ctxt.current_path) - 1);
		#endif

		if (rv < 0)
		{
#ifndef TEST
			__simple_printf("    dfd %d -> err %d!\n", args->dfd, rv);
#endif
			return rv;
		}
		
		// If we got "/", then turn it into "", because our algorithm will add a trailing slash later
		if (rv == 1 && ctxt.current_path[0] == '/')
		{
			ctxt.current_path[0] = '\0';
			ctxt.current_path_len = 0;
		}
		else
		{
			ctxt.current_path_len = rv;
			ctxt.current_path[rv] = '\0';
		}

		// Are we outside the vchrooted area already?
		if (ctxt.current_path_len < ctxt.current_root_len || strncmp(ctxt.current_path, ctxt.current_root, ctxt.current_root_len) != 0)
		{
			ctxt.current_root = "";
			ctxt.current_root_len = 0;
		}
	}

	int rv = vchroot_run(input_path, &ctxt);
	if (ctxt.current_path_len > 0)
		strcpy(args->path, ctxt.current_path);
	else
		strcpy(args->path, "/");

#ifndef TEST
	__simple_printf("    vchroot_expand(): rv=%d, expanded to %s\n", rv, args->path);
#endif

	return rv;
}

static int vchroot_run(const char* input_path, struct context* ctxt)
{
	if (*input_path == '/')
	{
		strcpy(ctxt->current_path, ctxt->current_root);
		ctxt->current_path_len = strlen(ctxt->current_path);
		input_path++;
	}

	const char* end;
	while (next_component(input_path, &end))
	{
		const unsigned int len = end - input_path;

		if ((len == 1 && input_path[0] == '.') || len == 0) // . or nothing (//)
		{
			// nothing to do
		}
		else
		{
			// append /
			ctxt->current_path[ctxt->current_path_len++] = '/';
			ctxt->current_path[ctxt->current_path_len] = '\0';

			if (len == 2 && input_path[0] == '.' && input_path[1] == '.') // ..
			{
				// Returning back into the vchrooted area
				if (ctxt->current_path_len <= 1)
				{
					strcpy(ctxt->current_path, prefix_path);
					strcat(ctxt->current_path, EXIT_PATH);
					ctxt->current_path_len = prefix_path_len + sizeof(EXIT_PATH);

					ctxt->current_path[ctxt->current_path_len-1] = '/';
					ctxt->current_path[ctxt->current_path_len] = '\0';

					ctxt->current_root = prefix_path;
					ctxt->current_root_len = prefix_path_len;
				}

				// current_path always ends with a slash
				// p points before the last /
				char* p = ctxt->current_path + ctxt->current_path_len - 2;

				while (true)
				{
					if (*p == '/')
					{
						*p = '\0';
						ctxt->current_path_len = p - ctxt->current_path;

						// We cannot exit current_root via ..
						if (ctxt->current_path_len < ctxt->current_root_len)
							return -LINUX_ENOENT;
						break;
					}
					p--;
				}
			}
			else
			{
				if (len + ctxt->current_path_len + 2 > sizeof(ctxt->current_path))
					return -LINUX_ENOENT;
				
				// Append the component
				const int prevlen = ctxt->current_path_len;

				memcpy(ctxt->current_path + ctxt->current_path_len, input_path, len);
				ctxt->current_path_len += len;
				ctxt->current_path[ctxt->current_path_len] = '\0';

				// Only analyze the last path component if we haven't had an unresolvent ENOENT before
				if (!ctxt->unknown_component)
				{
					stat_t st;
					#if defined(__NR_lstat)
						int status = LINUX_SYSCALL(__NR_lstat, ctxt->current_path, &st);
					#else
						#if __NR_newfstatat
							int status = LINUX_SYSCALL(__NR_newfstatat, LINUX_AT_FDCWD, ctxt->current_path, &st, LINUX_AT_SYMLINK_NOFOLLOW);
						#else
							int status = LINUX_SYSCALL(__NR_fstatat64, LINUX_AT_FDCWD, ctxt->current_path, &st, LINUX_AT_SYMLINK_NOFOLLOW);
						#endif
					#endif

                    if (status == -LINUX_ENOENT || status == -LINUX_ENAMETOOLONG)
                    {
                        int matched = vchroot_matching_component(ctxt, prevlen);
                        if (matched < 0) return matched;
                        if (!matched) ctxt->unknown_component = true;
                        else {
#if defined(__NR_lstat)
                            status = LINUX_SYSCALL(__NR_lstat, ctxt->current_path, &st);
#else
#if __NR_newfstatat
                            status = LINUX_SYSCALL(__NR_newfstatat, LINUX_AT_FDCWD, ctxt->current_path, &st, LINUX_AT_SYMLINK_NOFOLLOW);
#else
                            status = LINUX_SYSCALL(__NR_fstatat64, LINUX_AT_FDCWD, ctxt->current_path, &st, LINUX_AT_SYMLINK_NOFOLLOW);
#endif
#endif
                        }
                    }
					if (status == 0 && (st.st_mode & LINUX_S_IFMT) == LINUX_S_IFLNK)
					{
						// Follow symlink if follow is true or if we haven't reached the end of the input path yet
						if (ctxt->follow || *end)
						{
							char link[1024];
							int rv;

							#if defined(__NR_readlink)
								rv = LINUX_SYSCALL(__NR_readlink, ctxt->current_path, link, sizeof(link));
							#else
								rv = LINUX_SYSCALL(__NR_readlinkat, LINUX_AT_FDCWD, ctxt->current_path, link, sizeof(link));
							#endif

							if (rv < 0)
								return rv;
							if(rv>=sizeof(link))return -LINUX_ENAMETOOLONG;

							link[rv] = '\0';

                            const size_t private_proc_length = sizeof(DARLING_PROCFS_PATH) - 1;
                            const bool private_proc_link = prefix_path_len >= 0
                                && ctxt->current_path_len >= prefix_path_len + private_proc_length
                                && strncmp(ctxt->current_path, prefix_path, prefix_path_len) == 0
                                && strncmp(ctxt->current_path + prefix_path_len, DARLING_PROCFS_PATH, private_proc_length) == 0
                                && (ctxt->current_path[prefix_path_len + private_proc_length] == '/'
                                    || ctxt->current_path[prefix_path_len + private_proc_length] == '\0');
                            const bool proc_link = private_proc_link
                                || (strncmp(ctxt->current_path, "/proc", 5) == 0
                                    && (ctxt->current_path[5] == '/' || ctxt->current_path[5] == '\0'));

							// https://github.com/darlinghq/darling/issues/916
							// Special procfs hack due to the presence of broken symlinks in /proc/xxx/fd/ used to
							// point to sockets, pipes or anonymous inodes.
							if (proc_link)
							{
								if (strchr(link, ':') != 0)
								{
									goto ignore_symlink;
								}
							}

							// Remove the last component (because it will be substituted with symlink contents)
							if (link[0] != '/') // Only bother to do that if we know that the symlink is not absolute
							{
								ctxt->current_path_len = prevlen - 1; // kill the last slash as well
								ctxt->current_path[ctxt->current_path_len] = '\0';
							}

							// Symbolic link resolution
							const bool orig_follow = ctxt->follow;

							ctxt->follow = true;
							if(ctxt->symlinks_followed>=VCHROOT_MAX_SYMLINKS)return -LINUX_ELOOP;
							ctxt->symlinks_followed++;

							// resolve absolute symlinks within the prefix
							//
							// however, DON'T resolve `/proc` symlinks within the prefix.
							// anything under `/proc` is from Linux's `/proc` since we bind-mount it, so we can special-case them because we want those to be Linux-root relative.
							// see https://github.com/darlinghq/darling/issues/1052 for the issue this works around.
                            if (proc_link && link[0] == '/') {
                                // procfs targets are physical Linux paths, including
                                // files already unlinked but retained by an open FD.
                                ctxt->current_root = "";
                                ctxt->current_root_len = 0;
                            } else if (link[0] == '/' && !(strncmp(link, "/proc/", 6) == 0 || (rv == 5 && strncmp(link, "/proc", 5) == 0))) {
								ctxt->current_root = prefix_path;
								ctxt->current_root_len = prefix_path_len;
							}

							rv = vchroot_run(link, ctxt);

							ctxt->follow = orig_follow;

							if (rv != 0)
								return rv;
						}
					}
				}

ignore_symlink:

				if (ctxt->current_root_len > 0 && ctxt->current_path_len - ctxt->current_root_len == sizeof(EXIT_PATH)-1)
				{
					if (strncasecmp_l(ctxt->current_path + ctxt->current_root_len, EXIT_PATH, sizeof(EXIT_PATH) - 1, LC_C_LOCALE) == 0)
					{
						// Switch to the real system root
						ctxt->current_path[0] = '\0';
						ctxt->current_path_len = 0;
						ctxt->current_root = "";
						ctxt->current_root_len = 0;
					}
				}
			}
		}

		// Move on to the next component
		input_path = end;
		while (*input_path == '/')
			input_path++;
	}

	return 0;
}

static bool next_component(const char* from, const char** end)
{
	const char* pos = from;
	while (*pos != '/' && *pos)
		pos++;
	*end = pos;
	return *from;
}

int vchroot_fdpath(struct vchroot_fdpath_args* args)
{
#ifndef TEST
	if (prefix_path_len == -1)
		init_vchroot_path();
#endif

	char buf[50];
	char link[4096];

	__simple_sprintf(buf, "/proc/self/fd/%d", args->fd);

	#if defined(__NR_readlink)
		int rv = LINUX_SYSCALL(__NR_readlink, buf, link, sizeof(link) - 1);
	#else
		int rv = LINUX_SYSCALL(__NR_readlinkat, LINUX_AT_FDCWD, buf, link, sizeof(link) - 1);
	#endif
	if (rv < 0)
		return rv;

	link[rv] = '\0';

	if (rv >= prefix_path_len && strncmp(link, prefix_path, prefix_path_len) == 0 && (rv == prefix_path_len || link[prefix_path_len] == '/'))
	{
		if (args->maxlen-1 < rv - prefix_path_len)
			return -LINUX_ENAMETOOLONG;
		strcpy(args->path, link + prefix_path_len);

		if (args->path[0] == '\0')
			strcpy(args->path, "/");
	}
	else
	{
		if (args->maxlen < sizeof(EXIT_PATH) + rv)
			return -LINUX_ENAMETOOLONG;

		memcpy(args->path, EXIT_PATH, sizeof(EXIT_PATH) - 1);
		memcpy(args->path + sizeof(EXIT_PATH) - 1, link, rv+1);
	}

#ifndef TEST
	__simple_printf("fdpath %d -> %s\n", args->fd, args->path);
#endif

	return 0;
}

int vchroot_unexpand(struct vchroot_unexpand_args* args)
{
#ifndef TEST
    if (prefix_path_len == -1) init_vchroot_path();
#endif
    size_t n = strlen(args->path);
    if (n >= prefix_path_len && !strncmp(args->path, prefix_path, prefix_path_len) &&
        (n == prefix_path_len || args->path[prefix_path_len] == '/')) {
        memmove(args->path, args->path + prefix_path_len, n - prefix_path_len + 1);
        if (!args->path[0]) strcpy(args->path, "/");
    } else {
        if (n + sizeof(EXIT_PATH) > sizeof(args->path)) return -LINUX_ENAMETOOLONG;
        memmove(args->path + sizeof(EXIT_PATH) - 1, args->path, n + 1);
        memcpy(args->path, EXIT_PATH, sizeof(EXIT_PATH) - 1);
    }
    return 0;
}

#ifdef TEST
int main(int argc, const char** argv)
{
	if (argc != 3)
	{
		printf("Usage: vchroot_expand <vchroot_dir> <path_to_expand>\n");
		return 1;
	}

	int dfd = open(argv[1], O_RDONLY | O_DIRECTORY);
	__darling_vchroot(dfd);
	close(dfd);

	if (getenv("ICASE"))
		icase_enabled = true;

	struct vchroot_expand_args args;
	args.dfd = -100;
	strcpy(args.path, argv[2]);

	int rv = vchroot_expand(&args);
	printf("vchroot_expand() rv = %d\n", rv);
	printf("-> path = %s\n", args.path);

	if (rv == 0)
	{
		int fd = open(args.path, O_RDONLY);
		struct vchroot_fdpath_args fdpath_args;
		char buf[4096];

		fdpath_args.path = buf;
		fdpath_args.maxlen = sizeof(buf);
		fdpath_args.fd = fd;

		rv = vchroot_fdpath(&fdpath_args);

		printf("vchroot_fdpath() rv = %d\n", rv);
		if (rv >= 0)
			printf("-> path = %s\n", buf);

		close(fd);
	}
	
	return 0;
}
#endif
