#include "sockaddr-length-host-support.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <darling/emulation/xnu_syscall/bsd/helper/network/duct.h>
extern int __darling_vchroot(int);
int errno_linux_to_bsd(int value) { return value; } /* Host-only errno names. */
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"FAILED line%d: %s\n",__LINE__,#x);return 1; } }while(0)
static int address(struct sockaddr_fixup* out,const char* name,int nul,int full)
{
    struct sockaddr_fixup input;
    memset(&input,2,sizeof input);input.bsd_family=AF_UNIX;
    size_t length=strlen(name);memcpy(input.sun_path,name,length);
    if(nul)input.sun_path[length]=0;
    int extent=full?sizeof input:2+(int)length+nul;input.bsd_length=extent;
    memset(out,2,sizeof *out);
    /* Deterministic old converter overread: one 0x02 byte, then a terminator. */
    if(length+1<sizeof(out->sun_path))out->sun_path[length+1]=0;
    return sockaddr_fixup_from_bsd(out,&input,extent);
}
static int listener(const char* path)
{
    int fd=socket(AF_UNIX,SOCK_STREAM,0);assert(fd>=0);
    struct sockaddr_un addr={.sun_family=AF_UNIX};assert(strlen(path)<sizeof addr.sun_path);strcpy(addr.sun_path,path);unlink(path);
    assert(!bind(fd,(const struct sockaddr*)&addr,offsetof(struct sockaddr_un,sun_path)+strlen(path)+1));assert(!listen(fd,4));return fd;
}
int main(int argc,char** argv)
{
    CHECK(argc==3);const char* prefix=argv[1];int root=open(prefix,O_RDONLY|O_DIRECTORY);CHECK(root>=0);CHECK(!__darling_vchroot(root));close(root);
    char expected[256];snprintf(expected,sizeof expected,"%s/listener.sock",prefix);int server=listener(expected);struct sockaddr_fixup fixed;
    int length=address(&fixed,"/listener.sock",0,0);int client=socket(AF_UNIX,SOCK_STREAM,0);CHECK(client>=0);errno=0;int connected=connect(client,(const struct sockaddr*)&fixed,length);int code=errno;
    if(!strcmp(argv[2],"baseline")) { printf("OLD_NO_NUL_CONNECT result=%d errno=%d declared_length=%d\n",connected,code,length);close(client);close(server);unlink(expected);return connected<0 && code==ENOENT?0:1; }
    CHECK(length==2+strlen(expected));CHECK(connected==0);close(client);int accepted=accept(server,NULL,NULL);CHECK(accepted>=0);close(accepted);
    length=address(&fixed,"/listener.sock",1,0);CHECK(length==2+strlen(expected));client=socket(AF_UNIX,SOCK_STREAM,0);CHECK(connect(client,(const struct sockaddr*)&fixed,length)==0);close(client);accepted=accept(server,NULL,NULL);CHECK(accepted>=0);close(accepted);
    length=address(&fixed,"/listener.sock",1,1);CHECK(length==2+strlen(expected));CHECK(!memcmp(fixed.sun_path,expected,strlen(expected)));
    size_t page=sysconf(_SC_PAGESIZE);unsigned char* map=mmap(NULL,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);CHECK(map!=MAP_FAILED);CHECK(!mprotect(map+page,page,PROT_NONE));size_t n=strlen("/listener.sock");unsigned char* exact=map+page-2-n;exact[0]=2+n;exact[1]=AF_UNIX;memcpy(exact+2,"/listener.sock",n);memset(&fixed,2,sizeof fixed);length=sockaddr_fixup_from_bsd(&fixed,exact,2+n);CHECK(length==2+strlen(expected));CHECK(!memcmp(fixed.sun_path,expected,strlen(expected)));munmap(map,page*2);
    CHECK(sockaddr_fixup_from_bsd(&fixed,NULL,0)==-EINVAL);CHECK(sockaddr_fixup_from_bsd(&fixed,NULL,-1)==-EINVAL);CHECK(sockaddr_fixup_size_from_bsd(NULL,-1)==sizeof fixed);
    unsigned char too_big[513];memset(too_big,2,sizeof too_big);too_big[1]=AF_UNIX;CHECK(sockaddr_fixup_from_bsd(&fixed,too_big,sizeof fixed+1)==-EINVAL);CHECK(sockaddr_fixup_from_bsd(&fixed,too_big,sizeof too_big)==-EINVAL);
    char name[105];size_t capacity=sizeof fixed.sun_path;CHECK(strlen(prefix)+1<capacity);size_t logical=capacity-strlen(prefix);name[0]='/';memset(name+1,'a',logical-1);name[logical]=0;char longest[256];snprintf(longest,sizeof longest,"%s%s",prefix,name);int boundary=listener(longest);length=address(&fixed,name,0,0);CHECK(length==2+capacity);CHECK(!memcmp(fixed.sun_path,longest,capacity));client=socket(AF_UNIX,SOCK_STREAM,0);CHECK(connect(client,(const struct sockaddr*)&fixed,length)==0);close(client);accepted=accept(boundary,NULL,NULL);CHECK(accepted>=0);close(accepted);close(boundary);unlink(longest);
    name[logical]='b';name[logical+1]=0;CHECK(address(&fixed,name,0,0)==-ENAMETOOLONG);
    unsigned char ip[16]={16,AF_INET,0x12,0x34,127,0,0,1};memset(&fixed,0,sizeof fixed);CHECK(sockaddr_fixup_from_bsd(&fixed,ip,sizeof ip)==sizeof ip);CHECK(fixed.linux_family==AF_INET);CHECK(!memcmp((char*)&fixed+2,ip+2,sizeof ip-2));
    close(server);unlink(expected);printf("ACTUAL_SOCKADDR_LENGTH_%u_CHECKS_AND_LINUX_CONNECT_OK\n",checks);return 0;
}
