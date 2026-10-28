#define _GNU_SOURCE
#include "sysctl-net-host-support.h"
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netpacket/packet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>
extern int errno_linux_to_bsd(int);
void* native_dlopen(const char* path) { return dlopen(path,RTLD_NOW|RTLD_LOCAL); }
void* native_dlsym(void* handle,const char* name) { return dlsym(handle,name); }
int native_dlclose(void* handle) { return dlclose(handle); }
long sys_socket(int domain,int type,int protocol) { int r=socket(domain,type,protocol);return r<0?errno_linux_to_bsd(-errno):r; }
long close_internal(int fd) { return close(fd); }
long __real_ioctl(int fd,unsigned int command,void* arg) { int r=ioctl(fd,command,arg);return r<0?errno_linux_to_bsd(-errno):r; }
long sys_open_nocancel(const char* path,int flags,int mode) {
    (void)flags;(void)mode;size_t n=strlen(path);const char* net=strstr(path,"/net/");assert(net);
    char actual[128];snprintf(actual,sizeof actual,"/proc%s",net);int r=open(actual,O_RDONLY);return r<0?errno_linux_to_bsd(-errno):r;
}
long sys_read_nocancel(int fd,void* bytes,unsigned long length) { ssize_t r=read(fd,bytes,length);return r<0?errno_linux_to_bsd(-errno):r; }
unsigned long long __simple_atoi(const char* str,const char** end) { return strtoull(str,(char**)end,10); }
/* Historical negative control only reaches its unsupported-operation branch. */
int sockaddr_fixup_from_linux(void* out,const void* in,int size) { (void)out;(void)in;(void)size;abort(); }
static unsigned long long counter(const char* name,const char* which) {
    char path[256];snprintf(path,sizeof path,"/sys/class/net/%s/statistics/%s",name,which);FILE* f=fopen(path,"r");assert(f);unsigned long long n;assert(fscanf(f,"%llu",&n)==1);fclose(f);return n;
}
int host_interface_snapshot(const char* name,struct host_interface_snapshot* out) {
    memset(out,0,sizeof *out);struct ifaddrs* list;assert(getifaddrs(&list)==0);int found=0;
    for(struct ifaddrs* p=list;p;p=p->ifa_next) if(p->ifa_addr&&p->ifa_addr->sa_family==AF_PACKET&&!strcmp(p->ifa_name,name)) {
        struct sockaddr_ll* s=(void*)p->ifa_addr;out->index=s->sll_ifindex;out->flags=p->ifa_flags;out->hardware_type=s->sll_hatype;out->address_length=s->sll_halen;assert(s->sll_halen<=sizeof out->address);memcpy(out->address,s->sll_addr,s->sll_halen);found=1;break;
    }
    freeifaddrs(list);if(!found)return 0;int fd=socket(AF_INET,SOCK_DGRAM,0);assert(fd>=0);struct ifreq req={0};strncpy(req.ifr_name,name,sizeof req.ifr_name-1);assert(ioctl(fd,SIOCGIFMTU,&req)==0);out->mtu=req.ifr_mtu;close(fd);
    out->rx_bytes=counter(name,"rx_bytes");out->tx_bytes=counter(name,"tx_bytes");out->rx_packets=counter(name,"rx_packets");out->tx_packets=counter(name,"tx_packets");return 1;
}
unsigned int host_interface_count(void) {
    struct ifaddrs* list;assert(!getifaddrs(&list));unsigned int n=0;for(struct ifaddrs* p=list;p;p=p->ifa_next)if(p->ifa_addr&&p->ifa_addr->sa_family==AF_PACKET)n++;freeifaddrs(list);return n;
}

unsigned long long __simple_atoi16(const char* str,const char** end) { return strtoull(str,(char**)end,16); }
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
int host_route_present(unsigned int index,unsigned int family,const unsigned char* destination,const unsigned char* gateway,const unsigned char* mask) {
    int af=family==4?AF_INET:AF_INET6;size_t size=family==4?4:16;int fd=socket(AF_NETLINK,SOCK_RAW,NETLINK_ROUTE);assert(fd>=0);
    struct {struct nlmsghdr h;struct rtmsg r;} request={.h={.nlmsg_len=sizeof request,.nlmsg_type=RTM_GETROUTE,.nlmsg_flags=NLM_F_REQUEST|NLM_F_DUMP,.nlmsg_seq=17},.r={.rtm_family=af}};
    struct sockaddr_nl address={.nl_family=AF_NETLINK};assert(sendto(fd,&request,sizeof request,0,(void*)&address,sizeof address)==sizeof request);
    unsigned char buffer[32768];int done=0,found=0;
    while(!done){ssize_t length=recv(fd,buffer,sizeof buffer,0);assert(length>0);for(struct nlmsghdr* h=(void*)buffer;NLMSG_OK(h,length);h=NLMSG_NEXT(h,length)){
        if(h->nlmsg_type==NLMSG_DONE){done=1;break;}assert(h->nlmsg_type!=NLMSG_ERROR);if(h->nlmsg_type!=RTM_NEWROUTE)continue;
        struct rtmsg* route=NLMSG_DATA(h);if(route->rtm_family!=af)continue;unsigned int actual_index=0;unsigned char dst[16]={0},gw[16]={0},netmask[16]={0};
        int left=RTM_PAYLOAD(h);for(struct rtattr* a=RTM_RTA(route);RTA_OK(a,left);a=RTA_NEXT(a,left)){
            if(a->rta_type==RTA_OIF&&RTA_PAYLOAD(a)>=4)memcpy(&actual_index,RTA_DATA(a),4);
            if(a->rta_type==RTA_DST&&RTA_PAYLOAD(a)>=size)memcpy(dst,RTA_DATA(a),size);
            if(a->rta_type==RTA_GATEWAY&&RTA_PAYLOAD(a)>=size)memcpy(gw,RTA_DATA(a),size);
        }
        for(unsigned int bit=0;bit<route->rtm_dst_len;bit++)netmask[bit/8]|=0x80>>(bit%8);
        if(actual_index==index&&!memcmp(dst,destination,size)&&!memcmp(gw,gateway,size)&&!memcmp(netmask,mask,size))found=1;
    }}close(fd);return found;
}
