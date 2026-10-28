#include <mach-o/loader.h>
#include <mach-o/dyld.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
extern bool macho_source_version(const struct mach_header*,uint64_t*);
extern const struct mach_header_64 _mh_execute_header;
static unsigned checks;
static int verify(const char* name,const void* header,bool expected,uint64_t value)
{
    const uint64_t sentinel=UINT64_C(0xd15ea5edaf012345);
    uint64_t actual=sentinel;
    bool found=macho_source_version(header,&actual);
    ++checks;
    if(found!=expected || actual!=(expected?value:sentinel)) {
        fprintf(stderr,"FAIL %s found=%d value=%llx\n",name,found,(unsigned long long)actual);
        return 1;
    }
    return 0;
}
#define VERIFY(name,header,found,value) do { if(verify(name,header,found,value))return 1; }while(0)
int main(int argc,char** argv)
{
    if(argc!=3)return 2;
    void* owner=dlopen(argv[1],RTLD_LAZY|RTLD_LOCAL);
    if(!owner || dlsym(owner,"macho_source_version")!=(void*)macho_source_version) {
        fprintf(stderr,"Wrong source API owner: %s\n",dlerror());return 3;
    }
    ++checks;
    unsigned char buffer[256] __attribute__((aligned(16)));
    memset(buffer,0,sizeof buffer);
    struct mach_header_64* h=(struct mach_header_64*)buffer;
    h->magic=MH_MAGIC_64;h->cputype=CPU_TYPE_X86_64;h->filetype=MH_DYLIB;h->ncmds=1;h->sizeofcmds=sizeof(struct source_version_command);
    struct source_version_command* cmd=(struct source_version_command*)(buffer+sizeof(*h));
    cmd->cmd=LC_SOURCE_VERSION;cmd->cmdsize=sizeof(*cmd);cmd->version=UINT64_C(0x123456789abcdef0);
    VERIFY("64bit exact source value",h,true,cmd->version);
    cmd->version=0;VERIFY("present zero version",h,true,0);
    cmd->version=UINT64_MAX;VERIFY("full64bit value",h,true,UINT64_MAX);
    h->ncmds=0;VERIFY("no commands",h,false,0);h->ncmds=1;
    cmd->cmd=LC_UUID;VERIFY("no source command",h,false,0);cmd->cmd=LC_SOURCE_VERSION;
    h->magic=0x12345678;VERIFY("invalid magic",h,false,0);
    h->magic=MH_CIGAM;VERIFY("big endian32 rejected",h,false,0);
    h->magic=MH_CIGAM_64;VERIFY("big endian64 rejected",h,false,0);
    h->magic=0xcafebabe;VERIFY("fat magic rejected",h,false,0);h->magic=MH_MAGIC_64;
    h->filetype=13;VERIFY("invalid filetype",h,false,0);h->filetype=MH_DYLIB;
    h->sizeofcmds=0;VERIFY("zero command extent",h,false,0);h->sizeofcmds=sizeof(*cmd);
    cmd->cmdsize=4;VERIFY("short command rejected",h,false,0);
    cmd->cmdsize=256;VERIFY("oversized command rejected",h,false,0);cmd->cmdsize=sizeof(*cmd);
    struct source_version_command second=*cmd;second.version=123;
    cmd->version=456;memcpy(buffer+sizeof(*h)+sizeof(*cmd),&second,sizeof second);h->ncmds=2;h->sizeofcmds=2*sizeof(*cmd);
    VERIFY("first source wins",h,true,456);
    struct load_command skip={.cmd=LC_LOAD_DYLIB,.cmdsize=sizeof(skip)};
    memcpy(buffer+sizeof(*h),&skip,sizeof skip);memcpy(buffer+sizeof(*h)+sizeof skip,&second,sizeof second);
    h->sizeofcmds=sizeof skip+sizeof second;VERIFY("scan preceding command",h,true,123);
    struct mach_header h32={.magic=MH_MAGIC,.cputype=CPU_TYPE_I386,.filetype=MH_OBJECT,.ncmds=1,.sizeofcmds=sizeof(second)};
    memset(buffer,0,sizeof buffer);memcpy(buffer,&h32,sizeof h32);memcpy(buffer+sizeof h32,&second,sizeof second);
    VERIFY("32bit command layout",buffer,true,123);
    ((struct mach_header*)buffer)->ncmds=0;VERIFY("32bit no source",buffer,false,0);
    VERIFY("actual lld executable without source command",&_mh_execute_header,false,0);
    int fd=open(argv[2],O_RDONLY);
    struct stat st;
    if(fd<0 || fstat(fd,&st) || st.st_size<65536)return 5;
    void* original=mmap(NULL,65536,PROT_READ,MAP_PRIVATE,fd,0);
    close(fd);
    if(original==MAP_FAILED)return 6;
    const struct mach_header_64* originalHeader=original;
    if(originalHeader->magic!=MH_MAGIC_64 || originalHeader->sizeofcmds>65536-sizeof(*originalHeader))return 7;
    VERIFY("actual original Unity file source command",original,true,0);
    if(munmap(original,65536))return 8;
    if(dlclose(owner))return 4;
    printf("APPLE_DYLD_SOURCE_VERSION_ACTUAL_%u_CHECKS_OK\n",checks);
    return 0;
}
