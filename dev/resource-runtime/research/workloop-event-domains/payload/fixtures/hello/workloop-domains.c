#include <dlfcn.h>
#include <errno.h>
#include <mach/mach.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/event.h>
#define CHECK(x) do{if(!(x)){printf("FAILED line=%d errno=%d %s\n",__LINE__,errno,#x);return 1;}}while(0)
struct qos_event{uint64_t ident;int16_t filter;uint16_t flags;int32_t qos;uint64_t udata;uint32_t fflags,xflags;int64_t data;uint64_t ext[4];};
struct workq_config{uint32_t flags,version;void(*event)(void**,int*);void(*loop)(uint64_t*,void**,int*);void(*worker)(unsigned long);uint64_t serial,label;};
struct message{mach_msg_header_t h;uint64_t payload;};
static uint64_t ids[]={0x1234000056780001ull,0x1234000056780002ull};
static int pipes[2][2];static mach_port_t ports[2];static unsigned counts[2],mach_counts[2],entered,errors;
static pthread_t main_thread;
static unsigned char large_buffers[2][512];
static unsigned large_retries[2];
static void worker(unsigned long p){__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);}
static void workloop(uint64_t* id,void** ptr,int* count){
 unsigned slot=*id==ids[0]?0:*id==ids[1]?1:2;
 if(slot==2||pthread_equal(pthread_self(),main_thread)){__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);*count=0;return;}
 struct qos_event* ev=*ptr;int returned=0;
 for(int i=0;i<*count;i++){
  if(ev[i].filter==EVFILT_READ){
   if(ev[i].ident!=(uint64_t)pipes[slot][0]||ev[i].udata!=0x7000+slot)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   char ch;if(read(pipes[slot][0],&ch,1)!=1||ch!='a'+slot)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   __atomic_fetch_or(&entered,1u<<slot,__ATOMIC_RELEASE);
   for(unsigned spin=0;__atomic_load_n(&entered,__ATOMIC_ACQUIRE)!=3;spin++){if(spin>=10000){__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);break;}usleep(1000);}
   __atomic_add_fetch(&counts[slot],1,__ATOMIC_RELEASE);
  }else if(ev[i].filter==EVFILT_MACHPORT){
   if(ev[i].fflags==MACH_RCV_TOO_LARGE){
    if(ev[i].data!=ports[slot]||ev[i].ext[1]>sizeof large_buffers[slot])__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
    struct qos_event update=ev[i];update.flags=0x385;update.fflags=0x0700400e;update.data=0;update.ext[0]=(uintptr_t)large_buffers[slot];update.ext[1]=sizeof large_buffers[slot];update.ext[2]=update.ext[3]=0;ev[returned++]=update;
    __atomic_add_fetch(&large_retries[slot],1,__ATOMIC_RELAXED);continue;
   }
   unsigned index=__atomic_load_n(&mach_counts[slot],__ATOMIC_RELAXED);struct message* msg=(void*)(uintptr_t)ev[i].ext[0];
   if(ev[i].ident!=ports[slot]||ev[i].udata!=0x8000+slot||ev[i].fflags!=MACH_MSG_SUCCESS||!msg||msg->h.msgh_id!=(int)(3000+index)||msg->payload!=((uint64_t)slot<<32)+index)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   struct qos_event update=ev[i];update.flags=0x385;update.fflags=0x0700400e;update.data=0;update.ext[0]=update.ext[1]=update.ext[2]=update.ext[3]=0;ev[returned++]=update;
   __atomic_add_fetch(&mach_counts[slot],1,__ATOMIC_RELEASE);
  }else __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
 }
 *count=returned;
}
int main(void){
 setbuf(stdout,NULL);main_thread=pthread_self();
 int(*call)(uint64_t,const struct qos_event*,int,struct qos_event*,int,void*,unsigned long*,unsigned)=dlsym(RTLD_DEFAULT,"kevent_id");
 int(*setup)(struct workq_config*,size_t)=dlsym(RTLD_DEFAULT,"pthread_workqueue_setup");CHECK(call&&setup);
 int(*supported)(void)=dlsym(RTLD_DEFAULT,"_pthread_workqueue_supported");CHECK(supported&&supported()==0x400000d3);
 struct workq_config cfg={.version=2,.loop=workloop,.worker=worker};CHECK(setup(&cfg,sizeof cfg)==0);
 struct qos_event out[16];errno=0;CHECK(call(0,NULL,0,out,16,NULL,NULL,0x403)==-1&&errno==EINVAL);
 errno=0;CHECK(call(ids[0],NULL,0,out,16,NULL,NULL,0x20403)==-1&&errno==ENOENT);
 errno=0;CHECK(call(ids[0],NULL,0,out,16,NULL,NULL,0x400)==-1&&errno==EXDEV);
 for(unsigned slot=0;slot<2;slot++){
  CHECK(pipe(pipes[slot])==0);struct qos_event e={.ident=pipes[slot][0],.filter=EVFILT_READ,.flags=EV_ADD|EV_CLEAR,.udata=0x7000+slot};
  CHECK(call(ids[slot],&e,1,out,16,NULL,NULL,0x40403)==0);
  errno=0;CHECK(call(ids[slot],NULL,0,out,16,NULL,NULL,0x40403)==-1&&errno==EEXIST);
 }
 for(unsigned round=0;round<32;round++){
  for(unsigned slot=0;slot<2;slot++){char ch='a'+slot;CHECK(write(pipes[slot][1],&ch,1)==1);}
  for(unsigned slot=0;slot<2;slot++)for(unsigned spin=0;__atomic_load_n(&counts[slot],__ATOMIC_ACQUIRE)!=round+1;spin++){CHECK(spin<10000);usleep(1000);}
 }
 for(unsigned slot=0;slot<2;slot++){
  CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&ports[slot])==0);CHECK(mach_port_insert_right(mach_task_self(),ports[slot],ports[slot],MACH_MSG_TYPE_MAKE_SEND)==0);
  struct qos_event e={.ident=ports[slot],.filter=EVFILT_MACHPORT,.flags=0x385,.fflags=0x0700400e,.udata=0x8000+slot};CHECK(call(ids[slot],&e,1,out,16,NULL,NULL,0x20403)==0);
  CHECK(call(ids[slot],&e,1,out,16,NULL,NULL,0x20403)==0); /* update enabled subscription */
 }
 for(unsigned round=0;round<32;round++){
  for(unsigned slot=0;slot<2;slot++){struct message m={.h={.msgh_bits=MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0),.msgh_size=sizeof m,.msgh_remote_port=ports[slot],.msgh_id=3000+round},.payload=((uint64_t)slot<<32)+round};CHECK(mach_msg(&m.h,MACH_SEND_MSG,sizeof m,0,0,0,0)==0);}
  for(unsigned slot=0;slot<2;slot++)for(unsigned spin=0;__atomic_load_n(&mach_counts[slot],__ATOMIC_ACQUIRE)!=round+1;spin++){CHECK(spin<10000);usleep(1000);}
 }
 CHECK(errors==0&&counts[0]==32&&counts[1]==32&&mach_counts[0]==32&&mach_counts[1]==32&&entered==3&&large_retries[0]>0&&large_retries[1]>0);
 printf("WORKLOOP_LARGE_RETRIES %u %u\n",large_retries[0],large_retries[1]);
 puts("WORKLOOP_REAL_DISTINCT_IDS_CONCURRENT_CALLBACKS_PIPE_AND_MACH_OK domains=2 pipe=64 mach=64");return 0;
}
