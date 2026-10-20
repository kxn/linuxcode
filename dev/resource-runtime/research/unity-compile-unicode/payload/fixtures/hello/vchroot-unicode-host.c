#define _GNU_SOURCE
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define __simple_printf printf
#define LC_C_LOCALE 0
#define strncasecmp_l(a,b,n,l) strncasecmp(a,b,n)
#define TEST
#define LINUX_AT_FDCWD -100
#define LINUX_AT_SYMLINK_NOFOLLOW 0x100
#define __simple_abort abort
static int dserver_rpc_vchroot_path(char* a, size_t b, uint64_t* c) { abort(); }
#define main vchroot_old_test_main
#include "../../vendor/darling/src/external/xnu/darling/src/libsystem_kernel/emulation/src/linux_premigration/vchroot_userspace.c"
#undef main
int main(int argc,char** argv) {
 if(argc!=5) return 2;
 int fd=open(argv[1],O_RDONLY|O_DIRECTORY);
 if(fd<0) return 3;
 if(__darling_vchroot(fd)) return 4;
 close(fd);
 icase_enabled=atoi(argv[3]);
 struct vchroot_expand_args a={0};a.dfd=-100;a.flags=atoi(argv[4]);
 if(strlen(argv[2])>=1024)return 5;
 strcpy(a.path,argv[2]);int result=vchroot_expand(&a);
 printf("%d\n%s\n",result,a.path);return 0;
}
