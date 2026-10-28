/* Compile the exact production receive hook through receive-function.inc.
 * Real Linux sockets, SCM_RIGHTS, mmap, signals and ppoll execute. The peer
 * acknowledges only after receiving the actual S2C reply. A signal handler
 * uses the same receive hook, as the receive half of InterruptEnter does.
 * No production server protocol or Mach-O program is modified or executed. */
#define _GNU_SOURCE
#include <darlingserver/rpc-supplement.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <sys/poll.h>
#include <sys/types.h>
#include <fcntl.h>
#include <signal.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sched.h>

typedef uint64_t linux_sigset_t;
#define LINUX_SIGRTMIN SIGRTMIN
#define LINUX_EINTR EINTR
#define LINUX_EAGAIN EAGAIN
#define LINUX_EBADF EBADF
#define LINUX_MSG_DONTWAIT MSG_DONTWAIT
#define dserver_rpc_hooks_msghdr_t struct msghdr
#define dserver_rpc_hooks_cmsghdr_t struct cmsghdr
#define DSERVER_RPC_HOOKS_CMSG_FIRSTHDR CMSG_FIRSTHDR
#define DSERVER_RPC_HOOKS_SOL_SOCKET SOL_SOCKET
#define DSERVER_RPC_HOOKS_SCM_RIGHTS SCM_RIGHTS
#define DSERVER_RPC_HOOKS_CMSG_LEN CMSG_LEN
#define DSERVER_RPC_HOOKS_CMSG_DATA CMSG_DATA
#define dserver_rpc_hooks_memcpy memcpy
#define dserver_rpc_hooks_get_pid() getpid()
#define dserver_rpc_hooks_get_tid() ((int)syscall(SYS_gettid))
#define dserver_rpc_hooks_get_architecture() 2
#define dserver_rpc_hooks_get_server_address() NULL
#define dserver_rpc_hooks_get_server_address_length() 0
#define __simple_printf(...) fprintf(stderr,__VA_ARGS__)
#define __simple_abort() abort()
static int close_internal(int fd) { return close(fd); }

static int sockets[2], signal_number, mode_critical, mode_idle, mode_fd, mode_sequence;
static int mode_eagain, mode_send_error, mode_poll_error, mode_plain;
static pid_t main_tid;
static atomic_int wait_entered, handler_entered, injected, stop_peer, peer_done;
static unsigned ppoll_calls, eagain_count, map_count, reply_count;
static volatile sig_atomic_t signal_count, handler_bad;
static int transferred_fd=-1;
static void* mapped_address;
static void* protect_page;
static const char marker[]="actual-scm-rights-backing";

static void require(int value,const char* why) {
    if (!value) { fprintf(stderr,"FAIL %s maps=%u replies=%u signals=%d poll=%u eagain=%u\n",
                         why,map_count,reply_count,signal_count,ppoll_calls,eagain_count);fflush(NULL);_Exit(1); }
}
static long native_result(long value) { return value<0 ? -errno : value; }
static long fixture_syscall(long number,long a,long b,long c,long d,long e,long f) {
    if (number==SYS_ppoll) {
        ++ppoll_calls; atomic_store(&wait_entered,1);
        if (mode_poll_error) { mode_poll_error=0; return -EIO; }
    }
    if (number==SYS_recvmsg) {
        atomic_store(&wait_entered,1);
        if (mode_eagain && (c&MSG_DONTWAIT) && eagain_count==0) { ++eagain_count; return -EAGAIN; }
    }
    if (number==SYS_sendto && mode_send_error) { mode_send_error=0; return -EPIPE; }
    long value=native_result(syscall(number,a,b,c,d,e,f));
    if (number==SYS_mmap && (unsigned long)value<(unsigned long)-4096) {
        ++map_count; mapped_address=(void*)value;
    }
    if (number==SYS_recvmsg && value>=sizeof(dserver_s2c_callhdr_t)) {
        struct msghdr* message=(void*)b;
        dserver_s2c_callhdr_t* header=message->msg_iov[0].iov_base;
        if (header->call_number==0x52cca11 && header->s2c_number==dserver_s2c_msgnum_mmap) {
            struct cmsghdr* control=CMSG_FIRSTHDR(message);
            if (control && control->cmsg_level==SOL_SOCKET && control->cmsg_type==SCM_RIGHTS)
                memcpy(&transferred_fd,CMSG_DATA(control),sizeof(transferred_fd));
            if (mode_critical && !atomic_exchange(&injected,1))
                require(syscall(SYS_tgkill,getpid(),main_tid,signal_number)==0,"inject signal after recv");
        }
    }
    return value;
}
#define SC0(n) fixture_syscall(n,0,0,0,0,0,0)
#define SC1(n,a) fixture_syscall(n,(long)(a),0,0,0,0,0)
#define SC2(n,a,b) fixture_syscall(n,(long)(a),(long)(b),0,0,0,0)
#define SC3(n,a,b,c) fixture_syscall(n,(long)(a),(long)(b),(long)(c),0,0,0)
#define SC4(n,a,b,c,d) fixture_syscall(n,(long)(a),(long)(b),(long)(c),(long)(d),0,0)
#define SC5(n,a,b,c,d,e) fixture_syscall(n,(long)(a),(long)(b),(long)(c),(long)(d),(long)(e),0)
#define SC6(n,a,b,c,d,e,f) fixture_syscall(n,(long)(a),(long)(b),(long)(c),(long)(d),(long)(e),(long)(f))
#define SELECT_SC(_0,_1,_2,_3,_4,_5,_6,NAME,...) NAME
#define LINUX_SYSCALL(...) SELECT_SC(__VA_ARGS__,SC6,SC5,SC4,SC3,SC2,SC1,SC0)(__VA_ARGS__)
#define LINUX_SYSCALL1 SC1
#define LINUX_SYSCALL2 SC2
#define LINUX_SYSCALL3 SC3

#include "receive-function.inc"

static long receive_one(int fd) {
    unsigned char data[256]; unsigned char control[CMSG_SPACE(sizeof(int))*4];
    struct iovec iov={data,sizeof(data)};
    struct msghdr message={.msg_iov=&iov,.msg_iovlen=1,.msg_control=control,.msg_controllen=sizeof(control)};
    long value;
    do { value=dserver_rpc_hooks_receive_message(fd,&message); } while (value==-EINTR);
    return value;
}
static void signal_handler(int number) {
    (void)number; ++signal_count; atomic_store(&handler_entered,1);
    // The controlled peer will not release this acknowledgement until the
    // outstanding real mmap reply arrives, matching the production dependency.
    if (receive_one(sockets[0])!=8) handler_bad=1;
}
static void alarm_handler(int number) {
    (void)number;
    const char text[]="EXPECTED_DEADLOCK signal reentered after S2C recv, before reply\n";
    write(2,text,sizeof(text)-1);_Exit(42);
}
static void send_normal(void) {
    int value[2]={12345,0}; require(send(sockets[1],value,sizeof(value),0)==sizeof(value),"peer normal reply");
}
static void send_mmap(void) {
    dserver_s2c_call_mmap_t call={.header={0x52cca11,dserver_s2c_msgnum_mmap},
        .address=0,.length=4096,.protection=PROT_READ|PROT_WRITE,
        .flags=mode_fd?MAP_SHARED:MAP_PRIVATE|MAP_ANONYMOUS,.fd=mode_fd?0:-1,.offset=0};
    struct iovec iov={&call,sizeof(call)};
    unsigned char control[CMSG_SPACE(sizeof(int))];
    struct msghdr message={.msg_iov=&iov,.msg_iovlen=1};
    int backing=-1;
    if (mode_fd) {
        backing=syscall(SYS_memfd_create,"s2c-signal-test",MFD_CLOEXEC);
        require(backing>=0 && ftruncate(backing,4096)==0,"create real mmap backing");
        require(pwrite(backing,marker,sizeof(marker),0)==sizeof(marker),"write mmap backing");
        memset(control,0,sizeof(control)); message.msg_control=control;message.msg_controllen=sizeof(control);
        struct cmsghdr* c=CMSG_FIRSTHDR(&message);c->cmsg_level=SOL_SOCKET;c->cmsg_type=SCM_RIGHTS;
        c->cmsg_len=CMSG_LEN(sizeof(int));memcpy(CMSG_DATA(c),&backing,sizeof(backing));
    }
    require(sendmsg(sockets[1],&message,0)==sizeof(call),"peer S2C mmap");
    if (backing>=0) close(backing);
}
static void* peer(void* unused) {
    (void)unused;
    if (mode_idle) {
        while (!atomic_load(&wait_entered)) sched_yield();
        require(syscall(SYS_tgkill,getpid(),main_tid,signal_number)==0,"idle signal");
        while (!atomic_load(&handler_entered)) sched_yield();
    }
    if (mode_plain) { send_normal(); atomic_store(&peer_done,1);return NULL; }
    if (mode_sequence) {
        dserver_s2c_call_mprotect_t call={.header={0x52cca11,dserver_s2c_msgnum_mprotect},
            .address=(uintptr_t)protect_page,.length=4096,.protection=PROT_READ|PROT_WRITE};
        require(send(sockets[1],&call,sizeof(call),0)==sizeof(call),"peer S2C no-FD protection");
    } else send_mmap();
    while (!atomic_load(&stop_peer)) {
        struct pollfd fd={sockets[1],POLLIN,0};int n=poll(&fd,1,50);
        if (n<0 && errno==EINTR) continue;
        require(n>=0,"peer poll"); if (!n) continue;
        unsigned char bytes[128];ssize_t size=recv(sockets[1],bytes,sizeof(bytes),0);
        require(size>=sizeof(dserver_s2c_replyhdr_t),"peer reply size");
        dserver_s2c_replyhdr_t* header=(void*)bytes;
        require(header->call_number==0x52cca11,"peer real S2C reply header");
        ++reply_count;
        if (header->s2c_number==dserver_s2c_msgnum_mprotect) {
            require(size==sizeof(dserver_s2c_reply_mprotect_t) &&
                    ((dserver_s2c_reply_mprotect_t*)bytes)->return_value==0,"protection reply");
            send_mmap();continue;
        }
        require(header->s2c_number==dserver_s2c_msgnum_mmap && size==sizeof(dserver_s2c_reply_mmap_t),"mmap reply");
        dserver_s2c_reply_mmap_t* reply=(void*)bytes;
        require(reply->errno_result==0 && reply->address!=(uintptr_t)MAP_FAILED,"real mmap completed");
        if (mode_fd) require(memcmp((void*)reply->address,marker,sizeof(marker))==0,"real backing bytes");
        // InterruptEnter receive then original RPC receive, in that order.
        if (mode_idle || mode_critical) send_normal();
        send_normal();atomic_store(&peer_done,1);return NULL;
    }
    return NULL;
}
static int equal_mask(const sigset_t* a,const sigset_t* b) {
    for (int signal=1;signal<=64;++signal) if (sigismember(a,signal)!=sigismember(b,signal)) return 0;
    return 1;
}
int main(int argc,char** argv) {
    require(argc==2,"usage fixture CASE");const char* name=argv[1];main_tid=syscall(SYS_gettid);
    mode_critical=strstr(name,"critical")!=NULL;mode_idle=strstr(name,"idle")!=NULL;
    mode_fd=strstr(name,"fd")!=NULL;mode_sequence=!strcmp(name,"fd-after-no-fd");
    mode_eagain=!strcmp(name,"eagain");mode_send_error=!strcmp(name,"send-error");
    mode_poll_error=!strcmp(name,"poll-error");
    mode_plain=!strcmp(name,"normal") || mode_eagain || mode_poll_error;
    signal_number=strstr(name,"-rt")?SIGRTMIN+1:SIGCHLD;
    sigset_t initial,current;sigemptyset(&initial);sigaddset(&initial,SIGUSR2);sigaddset(&initial,SIGRTMIN);
    require(pthread_sigmask(SIG_SETMASK,&initial,NULL)==0,"initial signal mask");
    require(pthread_sigmask(SIG_SETMASK,NULL,&initial)==0,"query initial mask");
    struct sigaction sa={.sa_handler=signal_handler,.sa_flags=SA_RESTART};sigemptyset(&sa.sa_mask);
    require(sigaction(signal_number,&sa,NULL)==0,"install real signal handler");
    struct sigaction alarm_action={.sa_handler=alarm_handler};sigemptyset(&alarm_action.sa_mask);
    require(sigaction(SIGALRM,&alarm_action,NULL)==0,"alarm handler");alarm(3);
    if (!strcmp(name,"negative-fd") || !strcmp(name,"closed-fd")) {
        long status=receive_one(!strcmp(name,"negative-fd")?-1:1000000);
        require(status==-EBADF,"invalid fd status");
    } else {
        require(socketpair(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0,sockets)==0,"real socket pair");
        protect_page=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
        require(protect_page!=MAP_FAILED,"protection control page");
        pthread_t thread;require(pthread_create(&thread,NULL,peer,NULL)==0,"real peer thread");
        long status=receive_one(sockets[0]);
        if (!strcmp(name,"send-error")) require(status==-EPIPE,"send error propagated");
        else if (!strcmp(name,"poll-error") && ppoll_calls) require(status==-EIO,"poll error propagated");
        else require(status==8,"ordinary RPC acknowledgement");
        atomic_store(&stop_peer,1);require(pthread_join(thread,NULL)==0,"peer completed");
        if (mode_critical || mode_idle) require(signal_count==1 && !handler_bad,"signal reentry completed once");
        if (mode_eagain && ppoll_calls) require(eagain_count==1,"poll readiness race was exercised");
        if (mode_fd) require(transferred_fd>=0 && fcntl(transferred_fd,F_GETFD)==-1 && errno==EBADF,"received mmap FD closed");
        if (!mode_plain) require(map_count==1,"S2C mmap side effect executed exactly once");
        if (mapped_address) munmap(mapped_address,4096);munmap(protect_page,4096);
        close(sockets[0]);close(sockets[1]);
    }
    alarm(0);require(pthread_sigmask(SIG_SETMASK,NULL,&current)==0,"query restored mask");
    require(equal_mask(&initial,&current),"receive return failed to restore original signal mask");
    printf("PASS %s signals=%d maps=%u replies=%u ppoll=%u eagain=%u mask_restored=1\n",
           name,signal_count,map_count,reply_count,ppoll_calls,eagain_count);return 0;
}
