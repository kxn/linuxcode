#include <dlfcn.h>
#include <mach/mach.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/event.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) {printf("FAILED line=%d errno=%d %s\n",__LINE__,errno,#x); return 1;} } while(0)
struct qos_event { uint64_t ident; int16_t filter; uint16_t flags; int32_t qos; uint64_t udata; uint32_t fflags,xflags; int64_t data; uint64_t ext[4]; };
struct workq_config { uint32_t flags,version; void(*event)(void**,int*); void*workloop; void(*worker)(unsigned long); uint64_t serial,label; };
static int (*qevent)(int,const struct qos_event*,int,struct qos_event*,int,void*,unsigned long*,unsigned);
static unsigned long (*encode)(unsigned,int,unsigned long);
static int pipes[8][2];
static unsigned received, errors, worker_done, mach_received;
static mach_port_t message_port;
struct message { mach_msg_header_t h; uint64_t payload; };
static unsigned long expected_worker;
static pthread_t main_thread;
static void event_callback(void **ptr,int *count) {
    struct qos_event *events=*ptr;
    if (pthread_equal(pthread_self(),main_thread) || *count<1 || *count>16) __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
    for (int i=0;i<*count;i++) {
        struct qos_event *e=&events[i];
        if (e->udata == 0x456700) {
            struct message* msg=(void*)(uintptr_t)e->ext[0];
            unsigned index=__atomic_load_n(&mach_received,__ATOMIC_RELAXED);
            if (e->filter!=EVFILT_MACHPORT || e->ident!=message_port || e->fflags!=MACH_MSG_SUCCESS || !msg || msg->h.msgh_id!=(int)(1000+index) || msg->h.msgh_size!=sizeof(*msg) || msg->payload!=0x1234567800000000ull+index)
                __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
            __atomic_add_fetch(&mach_received,1,__ATOMIC_RELEASE);
            continue;
        }
        unsigned slot=(unsigned)e->udata-0x123400;
        if (slot>=8 || e->filter!=EVFILT_READ || e->ident!=(uint64_t)pipes[slot][0] || e->qos!=(int)encode(slot&1?0x05:0x21,0,0)) {
            __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);continue;
        }
        char byte;
        if (read(pipes[slot][0],&byte,1)!=1 || byte!='a'+slot) __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
        __atomic_add_fetch(&received,1,__ATOMIC_RELEASE);
    }
    *count=0;
}
static void worker_callback(unsigned long priority) {
    unsigned long tsd;
    __asm__("movq %%gs:32,%0":"=r"(tsd));
    if (priority!=expected_worker || tsd!=(expected_worker&~0x08000000ul)) __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
    __atomic_add_fetch(&worker_done,1,__ATOMIC_RELEASE);
}
int main(void) {
    setbuf(stdout,NULL);main_thread=pthread_self();
    void *p=dlopen("/usr/lib/system/libsystem_pthread.dylib",RTLD_LAZY|RTLD_LOCAL);CHECK(p);
    int (*supported)(void)=dlsym(p,"_pthread_workqueue_supported");
    int (*setup)(struct workq_config*,size_t)=dlsym(p,"pthread_workqueue_setup");
    int (*legacy)(int,unsigned long)=dlsym(p,"_pthread_workqueue_addthreads");
    int (*cooperative)(int,unsigned long)=dlsym(p,"_pthread_workqueue_add_cooperativethreads");
    encode=dlsym(p,"_pthread_qos_class_encode");qevent=dlsym(RTLD_DEFAULT,"kevent_qos");
    CHECK(setup&&supported&&encode&&qevent&&legacy&&cooperative);
    void* kernel=dlopen("/usr/lib/system/libsystem_kernel.dylib",RTLD_LAZY|RTLD_LOCAL);CHECK(kernel);
    const char* backend_names[]={"kqueue_impl","kevent_impl","kevent64_impl"};
    for(unsigned i=0;i<3;i++){void* fn=dlsym(kernel,backend_names[i]);Dl_info info;CHECK(fn&&dladdr(fn,&info)&&strstr(info.dli_fname,"libsystem_kernel.dylib"));printf("KQUEUE_BACKEND_PROVIDER %s %s\n",backend_names[i],info.dli_fname);}
    CHECK(supported()==0x40000053); /* no unimplemented workloop/ctl/SET_SELF */
    struct workq_config config={.version=2,.event=event_callback,.worker=worker_callback};
    CHECK(setup(&config,sizeof(config))==0);
    struct qos_event out[16];
    errno=0;CHECK(qevent(-1,NULL,-1,out,16,NULL,NULL,0x20)==-1&&errno==EINVAL);
    errno=0;CHECK(qevent(-1,NULL,0,out,16,NULL,NULL,0x420)==-1&&errno==ENOTSUP);
    unsigned long available=8;char scratch[8];
    errno=0;CHECK(qevent(-1,NULL,0,out,16,scratch,&available,0x20)==-1&&errno==ENOTSUP);
    for(unsigned slot=0;slot<8;slot++) {
        CHECK(pipe(pipes[slot])==0);
        struct qos_event change={.ident=pipes[slot][0],.filter=EVFILT_READ,.flags=EV_ADD|EV_CLEAR,.qos=(int32_t)encode(slot&1?0x05:0x21,0,0),.udata=0x123400+slot};
        CHECK(qevent(-1,&change,1,out,16,NULL,NULL,0x23)==0);
    }
    for(unsigned round=0;round<32;round++) {
        for(unsigned slot=0;slot<8;slot++){char ch='a'+slot;CHECK(write(pipes[slot][1],&ch,1)==1);}
        for(unsigned spin=0;__atomic_load_n(&received,__ATOMIC_ACQUIRE)!=(round+1)*8;spin++){CHECK(spin<10000);usleep(1000);}
    }
    CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&message_port)==KERN_SUCCESS);
    CHECK(mach_port_insert_right(mach_task_self(),message_port,message_port,MACH_MSG_TYPE_MAKE_SEND)==KERN_SUCCESS);
    struct qos_event mach_event={.ident=message_port,.filter=EVFILT_MACHPORT,.flags=EV_ADD|EV_CLEAR,.fflags=MACH_RCV_MSG|MACH_RCV_LARGE,.qos=(int32_t)encode(0x15,0,0),.udata=0x456700};
    CHECK(qevent(-1,&mach_event,1,out,16,NULL,NULL,0x23)==0);
    for(unsigned i=0;i<32;i++) {
        struct message msg={.h={.msgh_bits=MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0),.msgh_size=sizeof(msg),.msgh_remote_port=message_port,.msgh_id=1000+i},.payload=0x1234567800000000ull+i};
        CHECK(mach_msg(&msg.h,MACH_SEND_MSG,sizeof(msg),0,MACH_PORT_NULL,MACH_MSG_TIMEOUT_NONE,MACH_PORT_NULL)==MACH_MSG_SUCCESS);
        for(unsigned spin=0;__atomic_load_n(&mach_received,__ATOMIC_ACQUIRE)!=i+1;spin++){CHECK(spin<10000);usleep(1000);}
    }
    unsigned classes[]={0x05,0x09,0x11,0x15,0x19,0x21};
    for(unsigned i=0;i<192;i++) {
        expected_worker=encode(classes[i%6],0,0)|(i&1?0x08000000ul:0);
        CHECK((i&1?cooperative:legacy)(1,expected_worker&~0x08000000ul)==0);
        for(unsigned spin=0;__atomic_load_n(&worker_done,__ATOMIC_ACQUIRE)!=i+1;spin++){CHECK(spin<10000);usleep(1000);}
    }
    CHECK(errors==0 && received==256 && worker_done==192 && mach_received==32);
    puts("DIRECT_KEVENT_REAL_PIPE_MACH_CALLBACKS_AND_ALL_QOS_CLASSES_OK pipes=256 mach=32 workers=192");
    return 0;
}
