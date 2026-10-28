#ifndef LINUXCODE_SOCKADDR_HOST_SUPPORT
#define LINUXCODE_SOCKADDR_HOST_SUPPORT
#define _GNU_SOURCE
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#define LC_C_LOCALE 0
#define strncasecmp_l(a,b,n,l) strncasecmp(a,b,n)
#define LINUX_AT_FDCWD -100
#define LINUX_AT_SYMLINK_NOFOLLOW 0x100
#define __simple_abort abort
#define __simple_printf printf
#define _PER_THREAD_WD_H
static inline int get_perthread_wd(void) { return AT_FDCWD; }
static inline int dserver_rpc_vchroot_path(char* a,size_t b,uint64_t* c) { (void)a;(void)b;(void)c;abort(); }

#endif
