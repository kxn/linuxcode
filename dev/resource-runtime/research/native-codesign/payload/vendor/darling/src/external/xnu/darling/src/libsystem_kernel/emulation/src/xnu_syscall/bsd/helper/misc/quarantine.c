#include <darling/emulation/xnu_syscall/bsd/helper/misc/quarantine.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/common/simple.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/stat/common.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/xnu_syscall/bsd/impl/stat/fstatfs.h>
#include <darlingserver/rpc.h>
#include <sys/errno.h>
#include <sys/mount.h>
#include <stddef.h>

static const char physical_attribute[]="user.com.apple.quarantine";
struct policy {char identifier[256];unsigned char metadata[64],tracking[64];uint64_t args[8];};
static int ready_pid;
int quarantine_kernel_ready(void) {
#ifdef VARIANT_DYLD
    return -ENOTSUP;
#else
    int pid=LINUX_SYSCALL(__NR_getpid);
    if(__atomic_load_n(&ready_pid,__ATOMIC_ACQUIRE)==pid)return 0;
    int result=dserver_rpc_quarantine_kernel_ready(0x0001000f);
    if(!result)__atomic_store_n(&ready_pid,pid,__ATOMIC_RELEASE);
    return result?errno_linux_to_bsd(result):0;
#endif
}
static int get_policy(struct policy *p) {
    int result=quarantine_kernel_ready();if(result)return result;
    __builtin_memset(p,0,sizeof(*p));
    p->args[1]=(uintptr_t)p->identifier;p->args[3]=(uintptr_t)p->metadata;p->args[5]=(uintptr_t)p->tracking;
    int32_t error=0;result=dserver_rpc_mac_syscall("Quarantine",84,p->args,&error);
    if(result)return errno_linux_to_bsd(result);
    if(error==ENOATTR)return 0;
    if(error)return -error;
    if(p->args[0]>255||p->args[2]>64||p->args[4]||p->args[6]!=6)return -ENOTSUP;
    return 1;
}
int quarantine_process_active(void){struct policy p;return get_policy(&p);}
static char *hex(char *out,uint64_t value,unsigned width) {
    char reverse[16];unsigned n=0;
    do {reverse[n++]="0123456789abcdef"[value&15];value>>=4;}while(value);
    while(n<width)reverse[n++]='0';while(n)*out++=reverse[--n];return out;
}
/* Fixed-width hexadecimal fields used by the native kernel's
 * sscanf("%04x;%08lx"). The agent is copied after the second delimiter. */
static int scan_hex(const char *text,size_t length,size_t *position,unsigned width,uint64_t *value) {
    size_t at=*position;
    while(at<length&&(text[at]==' '||text[at]=='\t'||text[at]=='\n'))at++;
    size_t start=at;int negative=0;unsigned digits=0;uint64_t n=0;
    if(at<length&&width&&(text[at]=='+'||text[at]=='-')){negative=text[at]=='-';at++;width--;}
    while(at<length&&width&&text[at]){
        unsigned c=(unsigned char)text[at],d;
        if(c>='0'&&c<='9')d=c-'0';else if(c>='a'&&c<='f')d=c-'a'+10;else if(c>='A'&&c<='F')d=c-'A'+10;
        else if((c=='x'||c=='X')&&at==start+1&&text[start]=='0'){
            at++;width--;
            if(!width||at==length||!((text[at]>='0'&&text[at]<='9')||(text[at]>='a'&&text[at]<='f')||(text[at]>='A'&&text[at]<='F'))){at--;break;}
            continue;
        }else break;
        n=(n<<4)|d;digits++;at++;width--;
    }
    if(!digits)return -1;*value=negative?0-n:n;*position=at;return 0;
}
static int read_flags(const char *text,size_t length,unsigned *flags,size_t *suffix) {
    size_t at=0;uint64_t f,timestamp;
    if(scan_hex(text,length,&at,4,&f)||at==length||text[at]!=';')return -1;
    *suffix=at++;
    if(scan_hex(text,length,&at,8,&timestamp))return -1;
    while(at<length&&text[at]&&text[at]!=';')at++;
    if(at==length||text[at]!=';')return -1;
    *flags=f;return 0;
}
void quarantine_changed_fd(int fd,int operation) {
    struct policy p;int result=get_policy(&p);
    if(result<=0){if(result<0)__simple_printf("Quarantine: process label query failed: %d\n",-result);return;}
    struct linux_stat info;
#ifdef __NR_fstat64
    result=LINUX_SYSCALL(__NR_fstat64,fd,&info);
#else
    result=LINUX_SYSCALL(__NR_fstat,fd,&info);
#endif
    if(result<0)return;
    char original[1024],attribute[1100],*at;long length=-61;unsigned flags=6;size_t suffix=0;
    if(operation){
        length=LINUX_SYSCALL(__NR_fgetxattr,fd,physical_attribute,original,sizeof(original));
        if(length>=0){if(read_flags(original,length,&flags,&suffix))return;}
        else {if(operation==3)return;flags=0;}
        if(operation==2)flags&=~4u; // native rename removes the hard bit
        if(operation==3)flags&=~0x40u; // native link removes approval
        flags|=2; // supported processes have no actual Seatbelt restriction
    }
    if((flags&3)&&!(flags&0x40))flags|=0x80;
    at=hex(attribute,flags,4);
    if(length>=0){
        for(size_t i=suffix;i<(size_t)length;i++)*at++=original[i];
    }else{
        struct {long sec,usec;} now={0};
        if((info.st_mode&0170000)!=0040000)LINUX_SYSCALL(__NR_gettimeofday,&now,0);
        *at++=';';at=hex(at,now.sec,8);*at++=';';
        for(unsigned i=0;i<p.args[0];i++)*at++=p.identifier[i];*at++=';';
        if(!operation)for(unsigned i=0;i<p.args[2]&&p.metadata[i];i++)*at++=p.metadata[i];
    }
    result=LINUX_SYSCALL(__NR_fsetxattr,fd,physical_attribute,attribute,(at-attribute),0);
    if(result<0)__simple_printf("Quarantine: unable to update inode label: Linux errno %d\n",-result);
}
void quarantine_created_fd(int fd){quarantine_changed_fd(fd,0);}
void quarantine_changed_path(int dfd,const char *path,int nofollow,int operation) {
    if(quarantine_process_active()<=0)return;
    int fd=LINUX_SYSCALL(__NR_openat,dfd,path,0x80000|(nofollow?0x20000:0),0);
    if(fd<0)return;
    quarantine_changed_fd(fd,operation);LINUX_SYSCALL(__NR_close,fd);
}
void quarantine_created_path(int dfd,const char *path,int nofollow){quarantine_changed_path(dfd,path,nofollow,0);}
int quarantine_check_exec_fd(int fd) {
    char value[4096];long length=LINUX_SYSCALL(__NR_fgetxattr,fd,physical_attribute,value,sizeof(value));
    if(length==-61)return 0; // Linux ENODATA: no Quarantine attribute
    if(length<0)return -EPERM;
    unsigned flags;size_t suffix;
    if(read_flags(value,length,&flags,&suffix))return -EPERM;
    // The native hard bit denies exec even if the approved bit is also set.
    if(flags&4)return -EPERM;
    if(!(flags&2)||(flags&0x40))return 0;
    struct bsd_statfs64 fs;
    if(sys_fstatfs64(fd,&fs)==0&&(fs.f_flags&1))return 0;
    int active=quarantine_process_active();return active<0?active:active?-EPERM:0;
}
static int equal_name(const char *name,const char *literal) {
    // Check a caller pointer without turning an invalid xattr name into a
    // userspace crash. process_vm_readv on self has normal Linux EFAULT rules.
    for(size_t i=0;;i++){
        char c;struct {void *base;size_t length;} local={&c,1},remote={(void*)(name+i),1};
        long n=LINUX_SYSCALL(__NR_process_vm_readv,LINUX_SYSCALL(__NR_getpid),&local,1,&remote,1,0);
        if(n!=1)return -EFAULT;
        if(c!=literal[i])return 0;if(!c)return 1;
    }
}
int quarantine_xattr_name(const char *name,const char **translated,int writing) {
    int matches=equal_name(name,"com.apple.quarantine");if(matches<0)return matches;
    if(matches){
        *translated=physical_attribute;
        if(writing){int active=quarantine_process_active();if(active<0)return active;if(active)return -EPERM;}
    }else{
        matches=equal_name(name,"user.com.apple.quarantine");if(matches<0)return matches;
        *translated=matches?"user.user.com.apple.quarantine":name;
    }
    return 0;
}
void quarantine_removed_fd(int fd,const char *name){if(equal_name(name,"com.apple.quarantine")==1)quarantine_changed_fd(fd,4);}
void quarantine_removed_path(int dfd,const char *path,int nofollow,const char *name){if(equal_name(name,"com.apple.quarantine")==1)quarantine_changed_path(dfd,path,nofollow,4);}

/* Darwin names form one namespace. Linux requires a namespace prefix, so each
 * ordinary Darwin name is represented by an actual user.<name> inode xattr.
 * Retain the existing Quarantine policy and its protected alias handling. */
int darwin_xattr_name(const char *name,const char **translated,int writing,char storage[256]) {
    storage[0]='u';storage[1]='s';storage[2]='e';storage[3]='r';storage[4]='.';
    for(unsigned i=0;i<128;i++){
        char c;struct {void *base;size_t length;} local={&c,1},remote={(void*)(name+i),1};
        long n=LINUX_SYSCALL(__NR_process_vm_readv,LINUX_SYSCALL(__NR_getpid),&local,1,&remote,1,0);
        if(n!=1)return -EFAULT;
        storage[5+i]=c;
        if(!c){
            if(!i)return -EINVAL;
            /* Check the copied name so policy and physical lookup use one
             * snapshot even if another thread modifies the caller's bytes. */
            const char *logical=storage+5,*mapped;
            int result=quarantine_xattr_name(logical,&mapped,writing);
            if(result<0)return result;
            *translated=mapped==logical?storage:mapped;return 0;
        }
    }
    return -ENAMETOOLONG;
}

static long linux_xattr_list(const char *path,int fd,int nofollow,void *buffer,unsigned long size) {
    if(!path)return LINUX_SYSCALL(__NR_flistxattr,fd,buffer,size);
    return LINUX_SYSCALL(nofollow?__NR_llistxattr:__NR_listxattr,path,buffer,size);
}
long darwin_xattr_list(const char *path,int fd,int nofollow,char *output,unsigned long size) {
    long length=linux_xattr_list(path,fd,nofollow,0,0);
    if(length<0)return errno_linux_to_bsd(length);
    if(!length)return 0;
    if(length>65536)return -ERANGE;
    long allocation=LINUX_SYSCALL(__NR_mmap,0,length,3,0x22,-1,0);
    if(allocation<0&&allocation>=-4095)return errno_linux_to_bsd(allocation);
    char *names=(char*)allocation;long actual=linux_xattr_list(path,fd,nofollow,names,length),result=0;
    if(actual<0){result=errno_linux_to_bsd(actual);goto done;}
    for(long at=0;at<actual;){
        long start=at;while(at<actual&&names[at])at++;
        if(at==actual){result=-EIO;goto done;}
        long count=at-start;at++;
        if(count>5&&names[start]=='u'&&names[start+1]=='s'&&names[start+2]=='e'&&names[start+3]=='r'&&names[start+4]=='.'){
            for(long i=start+5;i<=start+count;i++)names[result++]=names[i];
        }
    }
    if(!size)goto done;
    if((unsigned long)result>size){result=-ERANGE;goto done;}
    if(result){
        struct {void *base;size_t length;} local={names,result},remote={output,result};
        long copied=LINUX_SYSCALL(__NR_process_vm_writev,LINUX_SYSCALL(__NR_getpid),&local,1,&remote,1,0);
        if(copied!=result)result=-EFAULT;
    }
done:
    LINUX_SYSCALL(__NR_munmap,names,length);return result;
}
