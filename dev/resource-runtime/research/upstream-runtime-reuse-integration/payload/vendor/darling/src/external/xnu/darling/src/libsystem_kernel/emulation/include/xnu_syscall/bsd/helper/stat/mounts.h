#ifndef DARLING_STAT_MOUNTS_H
#define DARLING_STAT_MOUNTS_H
#include <stddef.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/fcntl/open.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/linux_premigration/vchroot_expand.h>
#undef strlcpy
extern __SIZE_TYPE__ strlcpy(char *, const char *, __SIZE_TYPE__);
extern __SIZE_TYPE__ strlen(const char *);
extern int strncmp(const char *, const char *, __SIZE_TYPE__);
struct darling_mount_reader { int fd; long at, length; char input[512]; };
struct darling_mount_entry { char source[4096], target[4096], type[64]; };
static void darling_mount_unescape(char *s)
{
    char *out=s;
    while(*s) {
        if(s[0]=='\\'&&s[1]>='0'&&s[1]<='7'&&s[2]>='0'&&s[2]<='7'&&s[3]>='0'&&s[3]<='7') {
            *out++=((s[1]-'0')<<6)|((s[2]-'0')<<3)|(s[3]-'0');s+=4;
        } else *out++=*s++;
    }
    *out=0;
}
static long darling_mount_open(struct darling_mount_reader *r)
{
    r->at=r->length=0;
    r->fd=LINUX_SYSCALL(__NR_openat,-100,"/proc/self/mounts",LINUX_O_RDONLY|LINUX_O_CLOEXEC,0);
    return r->fd;
}
/* Keep the first three tokens; long mount options are discarded up to the
 * real newline rather than accidentally parsed as a new mount record. */
static long darling_mount_next(struct darling_mount_reader *r,struct darling_mount_entry *entry)
{
    unsigned field=0,used[3]={0,0,0};int token=0,overflow=0;
    char *fields[3]={entry->source,entry->target,entry->type};
    size_t capacities[3]={sizeof(entry->source),sizeof(entry->target),sizeof(entry->type)};
    for(;;) {
        if(r->at==r->length) {
            do { r->length=LINUX_SYSCALL(__NR_read,r->fd,r->input,sizeof(r->input)); } while(r->length==-4);
            r->at=0;if(r->length<=0)return r->length;
        }
        char c=r->input[r->at++];
        if(c=='\n') {
            if(overflow)return -36;
            if(field<3&&!token)continue;
            if(field<2)return -5;
            for(unsigned i=0;i<3;i++)fields[i][used[i]]=0;
            darling_mount_unescape(entry->source);darling_mount_unescape(entry->target);return 1;
        }
        if(c==' ') {if(token){field++;token=0;}continue;}
        token=1;
        if(field<3) {
            if(used[field]+1<capacities[field])fields[field][used[field]++]=c;
            else overflow=1;
        }
    }
}
static long darling_mount_guest_name(char *output,size_t size,const char *physical)
{
    struct vchroot_unexpand_args vc;
    if(strlcpy(vc.path,physical,sizeof(vc.path))>=sizeof(vc.path))return -36;
    long result=vchroot_unexpand(&vc);
    if(result<0)return result;
    /* The virtual host-root boundary may unexpand with a trailing slash.
     * statfs mount names are canonical paths: native DiskArbitration compares
     * them with realpath() using strcmp, including this exact boundary. */
    size_t length=strlen(vc.path);
    while(length>1 && vc.path[length-1]=='/')vc.path[--length]=0;
    if(strlcpy(output,vc.path,size)>=size)return -36;
    return 0;
}
static int darling_mount_contains(const char *mount,const char *path)
{
    size_t n=strlen(mount);
    return !strncmp(mount,path,n)&&(n==1||!path[n]||path[n]=='/');
}
#endif
