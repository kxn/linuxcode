/* Compiled with the actual Darwin SDK route headers; the Linux observer is a
 * separate translation unit. No copied/recreated Darwin routing structures. */
#include <darling/emulation/xnu_syscall/bsd/helper/misc/sysctl_net.h>
#include <net/route.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/if_types.h>
#include <netinet/in.h>
#include <sys/errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sysctl-net-host-support.h"
static unsigned checks;
#define CHECK(test) do {checks++;if(!(test)){printf("FAILED line%u %s\n",__LINE__,#test);return 1;}} while(0)
static long query(int family,int operation,int index,void* bytes,unsigned long* length) {
    int mib[]={4,17,0,family,operation,index};return sysctls_net[0].handler(mib,6,bytes,length,NULL,0);
}
int main(int argc,char** argv) {
    CHECK(argc==2);unsigned long length=0;
    if(!strcmp(argv[1],"baseline")){long r=query(0,6,0,NULL,&length);CHECK(r==-EINVAL);printf("OLD_IFLIST2_EINVAL_CONFIRMED\n");return 0;}
    CHECK(!query(0,6,0,NULL,&length));CHECK(length>sizeof(struct if_msghdr2));
    unsigned long capacity=length+4096;unsigned char* bytes=malloc(capacity+16);CHECK(bytes);memset(bytes,0xa7,capacity+16);length=capacity;CHECK(!query(0,6,0,bytes,&length));CHECK(length<=capacity);
    for(unsigned i=0;i<16;i++)CHECK(bytes[capacity+i]==0xa7);
    unsigned count=0,addresses=0,ipv4=0,ipv6=0;unsigned last_index=0;
    for(unsigned long pos=0;pos<length;) {
        struct if_msghdr* common=(void*)(bytes+pos);CHECK(common->ifm_msglen>=sizeof(struct ifa_msghdr));CHECK(common->ifm_msglen<=length-pos);CHECK(common->ifm_version==RTM_VERSION);
        if(common->ifm_type==RTM_IFINFO2){
            struct if_msghdr2* h=(void*)common;CHECK(h->ifm_msglen>=sizeof *h+sizeof(struct sockaddr_dl));struct sockaddr_dl* dl=(void*)((char*)h+sizeof *h);CHECK(dl->sdl_family==AF_LINK);CHECK(dl->sdl_nlen>0&&dl->sdl_nlen<16);char name[16]={0};memcpy(name,dl->sdl_data,dl->sdl_nlen);struct host_interface_snapshot actual;CHECK(host_interface_snapshot(name,&actual));
            CHECK(h->ifm_index==actual.index);CHECK(dl->sdl_index==actual.index);CHECK(h->ifm_flags&IFF_UP?actual.flags&1:!(actual.flags&1));CHECK(h->ifm_flags&IFF_MULTICAST?actual.flags&0x1000:!(actual.flags&0x1000));CHECK(h->ifm_data.ifi_mtu==actual.mtu);CHECK(dl->sdl_alen==actual.address_length);CHECK(!memcmp(LLADDR(dl),actual.address,dl->sdl_alen));CHECK(h->ifm_data.ifi_ibytes<=actual.rx_bytes);CHECK(h->ifm_data.ifi_obytes<=actual.tx_bytes);CHECK(h->ifm_data.ifi_ipackets<=actual.rx_packets);CHECK(h->ifm_data.ifi_opackets<=actual.tx_packets);
            if(actual.hardware_type==772)CHECK(h->ifm_data.ifi_type==IFT_LOOP);if(actual.hardware_type==1)CHECK(h->ifm_data.ifi_type==IFT_ETHER);
            unsigned long selected_length=0;CHECK(!query(0,6,h->ifm_index,NULL,&selected_length));CHECK(selected_length);void* selected=malloc(selected_length+4096);CHECK(selected);selected_length+=4096;CHECK(!query(0,6,h->ifm_index,selected,&selected_length));for(unsigned long at=0;at<selected_length;){struct if_msghdr* s=(void*)((char*)selected+at);CHECK(s->ifm_index==h->ifm_index);CHECK(s->ifm_msglen);at+=s->ifm_msglen;}free(selected);
            last_index=h->ifm_index;count++;
        }else{CHECK(common->ifm_type==RTM_NEWADDR);struct ifa_msghdr* h=(void*)common;CHECK(h->ifam_index==last_index);CHECK(h->ifam_addrs&RTA_IFA);unsigned long at=sizeof *h;for(unsigned bit=1;bit<=RTA_BRD;bit<<=1){if(!(h->ifam_addrs&bit))continue;CHECK(at<common->ifm_msglen);struct sockaddr* s=(void*)((char*)h+at);CHECK(s->sa_len==sizeof(struct sockaddr_in)||s->sa_len==sizeof(struct sockaddr_in6));CHECK(s->sa_family==AF_INET||s->sa_family==AF_INET6);if(bit==RTA_IFA){if(s->sa_family==AF_INET)ipv4++;else ipv6++;}at+=(s->sa_len+3)&~3;}CHECK(at==common->ifm_msglen);addresses++;}
        pos+=common->ifm_msglen;
    }
    CHECK(count==host_interface_count());CHECK(count>0);CHECK(addresses>0);
    unsigned char tiny[32];memset(tiny,0x6d,sizeof tiny);unsigned long small=1;CHECK(query(0,6,0,tiny,&small)==-ENOMEM);CHECK(small>1);for(unsigned i=0;i<sizeof tiny;i++)CHECK(tiny[i]==0x6d);
    unsigned long old_length=0;CHECK(!query(0,3,0,NULL,&old_length));unsigned char* old=malloc(old_length+4096);CHECK(old);old_length+=4096;CHECK(!query(0,3,0,old,&old_length));unsigned old_count=0;for(unsigned long pos=0;pos<old_length;){struct if_msghdr* h=(void*)(old+pos);CHECK(h->ifm_msglen>0);if(h->ifm_type==RTM_IFINFO)old_count++;else CHECK(h->ifm_type==RTM_NEWADDR);pos+=h->ifm_msglen;}CHECK(old_count==count);free(old);
    for(unsigned n=0;n<2;n++){unsigned long size=0;int family=n?AF_INET6:AF_INET;CHECK(!query(family,6,0,NULL,&size));unsigned char* filtered=malloc(size+4096);CHECK(filtered);size+=4096;CHECK(!query(family,6,0,filtered,&size));for(unsigned long pos=0;pos<size;){struct if_msghdr* h=(void*)(filtered+pos);if(h->ifm_type==RTM_NEWADDR){struct sockaddr* a=(void*)((char*)h+sizeof(struct ifa_msghdr));CHECK(a->sa_family==family);}CHECK(h->ifm_msglen);pos+=h->ifm_msglen;}free(filtered);}
    unsigned long routes_size=0;CHECK(!query(0,1,0,NULL,&routes_size));unsigned char* routes=malloc(routes_size+4096);CHECK(routes);routes_size+=4096;CHECK(!query(0,1,0,routes,&routes_size));unsigned route_count=0,active_routes=0,gateways=0;
    for(unsigned long pos=0;pos<routes_size;){struct rt_msghdr* h=(void*)(routes+pos);CHECK(h->rtm_msglen>=sizeof *h);CHECK(h->rtm_msglen<=routes_size-pos);CHECK(h->rtm_version==RTM_VERSION);CHECK(h->rtm_type==RTM_GET);CHECK(h->rtm_addrs&RTA_DST);CHECK(h->rtm_addrs&RTA_NETMASK);unsigned long at=sizeof *h;const unsigned char *destination=NULL,*gateway=NULL,*netmask=NULL;unsigned char zero[16]={0};int family=0;
        for(unsigned bit=1;bit<=RTA_NETMASK;bit<<=1){if(!(h->rtm_addrs&bit))continue;CHECK(at<h->rtm_msglen);struct sockaddr* a=(void*)((char*)h+at);CHECK(a->sa_family==AF_INET||a->sa_family==AF_INET6);CHECK(!family||family==a->sa_family);family=a->sa_family;const unsigned char* address=family==AF_INET?(const void*)&((struct sockaddr_in*)a)->sin_addr:(const void*)&((struct sockaddr_in6*)a)->sin6_addr;if(bit==RTA_DST)destination=address;if(bit==RTA_GATEWAY){gateway=address;gateways++;}if(bit==RTA_NETMASK)netmask=address;CHECK(a->sa_len==(family==AF_INET?sizeof(struct sockaddr_in):sizeof(struct sockaddr_in6)));at+=(a->sa_len+3)&~3;}
        CHECK(at==h->rtm_msglen);CHECK(destination&&netmask);if(h->rtm_flags&RTF_UP){CHECK(host_route_present(h->rtm_index,family==AF_INET?4:6,destination,gateway?gateway:zero,netmask));active_routes++;}route_count++;pos+=h->rtm_msglen;
    }
    CHECK(route_count>0);CHECK(active_routes>0);free(routes);small=1;CHECK(query(0,1,0,tiny,&small)==-ENOMEM);CHECK(small>1);
    int mib[]={4,17,0,0,6,0};CHECK(sysctls_net[0].handler(mib,5,NULL,&length,NULL,0)==-EINVAL);CHECK(sysctls_net[0].handler(mib,6,NULL,NULL,NULL,0)==-EINVAL);CHECK(sysctls_net[0].handler(mib,6,NULL,&length,bytes,1)==-EPERM);CHECK(query(0,99,0,NULL,&length)==-EINVAL);
    printf("ACTUAL_ROUTES count=%u active=%u gateways=%u\n",route_count,active_routes,gateways);free(bytes);printf("ACTUAL_SYSCTL_NET_%u_CHECKS interfaces=%u addresses=%u ipv4=%u ipv6=%u\n",checks,count,addresses,ipv4,ipv6);return 0;
}
