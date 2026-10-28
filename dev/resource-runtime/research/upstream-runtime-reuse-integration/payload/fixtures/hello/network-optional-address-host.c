#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <unistd.h>
#include <darling/emulation/xnu_syscall/bsd/helper/network/duct.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/accept.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/recvfrom.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/recvmsg.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/sendmsg.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/sendto.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/getpeername.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/getsockname.h>
static unsigned checks,linux_calls;static int uncanceled=1;
#define CHECK(x) do { checks++;if(!(x)){fprintf(stderr,"FAILED line%d: %s\n",__LINE__,#x);return 1;} }while(0)
/* Host ABI bridges call the real Linux kernel; no network syscall is mocked. */
long linux_syscall(long a,long b,long c,long d,long e,long f,int nr){linux_calls++;long r=syscall(nr,a,b,c,d,e,f);return r<0?-errno:r;}
int errno_linux_to_bsd(int value){return value;}
long sys_pthread_canceled(int action){(void)action;return uncanceled;}
long sys_fcntl_nocancel(int fd,int cmd,long arg){if(cmd==F_SETFL)arg=(arg&~4L)|((arg&4)?O_NONBLOCK:0);long r=fcntl(fd,cmd,arg);if(r<0)return -errno;if(cmd==F_GETFL)r=(r&~O_NONBLOCK)|((r&O_NONBLOCK)?4:0);return r;}
static void tick(int sig){(void)sig;}
static int peer(int listener,const struct sockaddr_un* name){int c=socket(AF_UNIX,SOCK_STREAM,0);assert(c>=0);assert(connect(c,(void*)name,sizeof *name)==0);return c;}
int main(int argc,char**argv){CHECK(argc==3);int s=socket(AF_UNIX,SOCK_STREAM,0);CHECK(s>=0);struct sockaddr_un name={.sun_family=AF_UNIX};CHECK(strlen(argv[1])+3<sizeof name.sun_path);snprintf(name.sun_path,sizeof name.sun_path,"%s/s",argv[1]);CHECK(bind(s,(void*)&name,sizeof name)==0);CHECK(listen(s,8)==0);
 if(!strcmp(argv[2],"baseline-accept")){int c=peer(s,&name);(void)c;long fd=sys_accept_nocancel(s,NULL,NULL);fprintf(stderr,"OLD_ACCEPT_UNEXPECTEDLY_RETURNED %ld\n",fd);return 3;}
 int pair[2];CHECK(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);char tx='A',rx=0;
 if(!strcmp(argv[2],"baseline-sendto")){long n=sys_sendto_nocancel(pair[0],&tx,1,0,NULL,1024);printf("OLD_NULL_ADDRESS_IGNORED_LENGTH_SENDTO %ld\n",n);return n==-EINVAL?0:5;}
 struct iovec io={.iov_base=&tx,.iov_len=1};struct bsd_msghdr msg={.msg_name=NULL,.msg_namelen=16,.msg_iov=&io,.msg_iovlen=1};
 if(!strcmp(argv[2],"baseline-sendmsg")){long n=sys_sendmsg_nocancel(pair[0],&msg,0);printf("OLD_NULL_NAME_NONZERO_LENGTH_SENDMSG %ld\n",n);return n==-EFAULT?0:4;}
 int c=peer(s,&name);int a=sys_accept_nocancel(s,NULL,NULL);CHECK(a>=0);CHECK(write(c,&tx,1)==1);CHECK(read(a,&rx,1)==1 && rx==tx);close(a);close(c);
 int ignored=12345;c=peer(s,&name);a=sys_accept_nocancel(s,NULL,&ignored);CHECK(a>=0);CHECK(ignored==12345);close(a);close(c);
 struct sockaddr_un address;int extent=sizeof address;c=peer(s,&name);a=sys_accept_nocancel(s,&address,&extent);CHECK(a>=0);CHECK(extent==2);CHECK(((struct sockaddr_fixup*)&address)->bsd_family==AF_UNIX);CHECK(((struct sockaddr_fixup*)&address)->bsd_length==extent);close(a);close(c);
 CHECK(fcntl(s,F_SETFL,O_NONBLOCK)==0);c=peer(s,&name);a=sys_accept_nocancel(s,NULL,NULL);CHECK(a>=0);CHECK(fcntl(a,F_GETFL)&O_NONBLOCK);close(a);close(c);CHECK(sys_accept_nocancel(s,NULL,NULL)==-EAGAIN);CHECK(fcntl(s,F_SETFL,0)==0);
 CHECK(sys_accept_nocancel(-1,NULL,NULL)==-EBADF);struct sigaction action={.sa_handler=tick};CHECK(sigaction(SIGALRM,&action,NULL)==0);alarm(1);CHECK(sys_accept_nocancel(s,NULL,NULL)==-EINTR);alarm(0);uncanceled=0;unsigned before=linux_calls;CHECK(sys_accept(s,NULL,NULL)==-EINTR);CHECK(linux_calls==before);uncanceled=1;
 CHECK(sys_sendmsg_nocancel(pair[0],&msg,0)==1);CHECK(read(pair[1],&rx,1)==1 && rx==tx);msg.msg_namelen=0;CHECK(sys_sendmsg_nocancel(pair[0],&msg,0)==1);CHECK(read(pair[1],&rx,1)==1);CHECK(sys_sendto_nocancel(pair[0],&tx,1,0,NULL,0)==1);CHECK(sys_sendto_nocancel(pair[0],&tx,1,0,NULL,1024)==1);CHECK(read(pair[1],&rx,1)==1);CHECK(sys_recvfrom_nocancel(pair[1],&rx,1,0,NULL,NULL)==1);CHECK(rx==tx);
 CHECK(write(pair[0],&tx,1)==1);ignored=99;CHECK(sys_recvfrom_nocancel(pair[1],&rx,1,0,NULL,&ignored)==1);CHECK(ignored==99);struct iovec receive={.iov_base=&rx,.iov_len=1};struct bsd_msghdr received={.msg_name=NULL,.msg_namelen=16,.msg_iov=&receive,.msg_iovlen=1};CHECK(write(pair[0],&tx,1)==1);CHECK(sys_recvmsg_nocancel(pair[1],&received,0)==1);CHECK(received.msg_name==NULL);CHECK(received.msg_namelen==16);uncanceled=0;before=linux_calls;CHECK(sys_recvfrom(pair[1],&rx,1,0,NULL,NULL)==-EINTR);CHECK(sys_recvmsg(pair[1],&received,0)==-EINTR);CHECK(sys_sendmsg(pair[0],&msg,0)==-EINTR);CHECK(linux_calls==before);uncanceled=1;
 extent=sizeof address;CHECK(sys_getsockname(pair[0],NULL,&extent)==-EFAULT);extent=sizeof address;CHECK(sys_getpeername(pair[0],NULL,&extent)==-EFAULT);CHECK(sys_getsockname(pair[0],NULL,NULL)==-EFAULT);CHECK(sys_getpeername(pair[0],NULL,NULL)==-EFAULT);
 int udp=socket(AF_INET,SOCK_DGRAM,0);CHECK(udp>=0);struct sockaddr_in ip={.sin_family=AF_INET,.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};CHECK(bind(udp,(void*)&ip,sizeof ip)==0);socklen_t iplen=sizeof ip;CHECK(getsockname(udp,(void*)&ip,&iplen)==0);struct sockaddr_fixup bsd;extent=sizeof bsd;CHECK(sys_getsockname(udp,&bsd,&extent)==0);CHECK(extent==sizeof ip);CHECK(bsd.bsd_family==AF_INET);int sender=socket(AF_INET,SOCK_DGRAM,0);CHECK(sender>=0);CHECK(sendto(sender,&tx,1,0,(void*)&ip,sizeof ip)==1);extent=sizeof bsd;CHECK(sys_recvfrom_nocancel(udp,&rx,1,0,&bsd,&extent)==1);CHECK(extent==sizeof ip);CHECK(bsd.bsd_family==AF_INET);CHECK(bsd.bsd_length==sizeof ip);
 close(sender);close(udp);close(pair[0]);close(pair[1]);close(s);unlink(name.sun_path);printf("NETWORK_OPTIONAL_ADDRESS_%u_CHECKS_REAL_LINUX_OK\n",checks);return 0;}
