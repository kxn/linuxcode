#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/event.h>
#define CHECK(x) do{if(!(x)){printf("FAILED line=%d errno=%d %s\n",__LINE__,errno,#x);return 1;}}while(0)
struct event{uint64_t ident;int16_t filter;uint16_t flags;int32_t qos;uint64_t udata;uint32_t fflags,xflags;int64_t data;uint64_t ext[4];};
struct config{uint32_t flags,version;void(*event)(void**,int*);void(*loop)(uint64_t*,void**,int*);void(*worker)(unsigned long);uint64_t serial,label;};
static uint64_t ids[]={0x1234999911110001ull,0x1234999911110002ull},states[2];
static unsigned calls[2],running[2],blocked[2],pause_callbacks,errors,pipe_calls[2];
static uint64_t last_value[2];static int pipes[2][2];
static void worker(unsigned long p){__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);}
static void callback(uint64_t* id,void** ptr,int* count){
 unsigned slot=*id==ids[0]?0:*id==ids[1]?1:2;
 if(slot==2){__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);*count=0;return;}
 if(__atomic_add_fetch(&running[slot],1,__ATOMIC_ACQ_REL)!=1)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
 struct event* ev=*ptr;
 for(int i=0;i<*count;i++){
  if(ev[i].filter==-17){
   if(ev[i].ident!=ids[slot]||ev[i].udata!=ids[slot]||ev[i].flags&EV_ERROR||!(ev[i].fflags&1)||(ev[i].qos!=0x2000&&ev[i].qos!=0x1000))__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   last_value[slot]=ev[i].ext[3];__atomic_add_fetch(&calls[slot],1,__ATOMIC_RELEASE);
   if(__atomic_load_n(&pause_callbacks,__ATOMIC_ACQUIRE)){__atomic_store_n(&blocked[slot],1,__ATOMIC_RELEASE);while(__atomic_load_n(&pause_callbacks,__ATOMIC_ACQUIRE))usleep(1000);}
  }else if(ev[i].filter==EVFILT_READ){
   char ch;if(ev[i].ident!=pipes[slot][0]||read(pipes[slot][0],&ch,1)!=1||ch!='a'+slot)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   __atomic_add_fetch(&pipe_calls[slot],1,__ATOMIC_RELEASE);
  }else __atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
 }
 __atomic_sub_fetch(&running[slot],1,__ATOMIC_RELEASE);*count=0;
}
static int wait_for(unsigned* address,unsigned value){for(int i=0;i<10000;i++){if(__atomic_load_n(address,__ATOMIC_ACQUIRE)==value)return 1;usleep(1000);}return 0;}
static struct event request(unsigned slot,uint64_t value){return(struct event){.ident=ids[slot],.filter=-17,.flags=EV_ADD|EV_ENABLE,.qos=0x2000,.udata=ids[slot],.fflags=0x111,.ext={0,(uintptr_t)&states[slot],UINT64_MAX,value}};}
int main(void){
 setbuf(stdout,NULL);
 int(*call)(uint64_t,const struct event*,int,struct event*,int,void*,unsigned long*,unsigned)=dlsym(RTLD_DEFAULT,"kevent_id");
 int(*setup)(struct config*,size_t)=dlsym(RTLD_DEFAULT,"pthread_workqueue_setup");CHECK(call&&setup);struct config cfg={.version=2,.loop=callback,.worker=worker};CHECK(setup(&cfg,sizeof cfg)==0);
 struct event out[8];
 for(unsigned s=0;s<2;s++){
  CHECK(pipe(pipes[s])==0);struct event ev={.ident=pipes[s][0],.filter=EVFILT_READ,.flags=EV_ADD|EV_CLEAR};CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==0);
  states[s]=42;ev=request(s,41);ev.fflags&=~0x100;CHECK(call(ids[s],&ev,1,&ev,1,NULL,NULL,0x403)==1&&(ev.flags&EV_ERROR)&&ev.data==ESTALE&&ev.ext[3]==42);
  ev=request(s,41);CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==0); /* stale ignored: no attach or activation */
  ev=request(s,42);ev.ext[1]=8;CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==1&&out[0].data==EFAULT);
  ev=request(s,42);ev.ext[1]++;CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==1&&out[0].data==EINVAL);
  ev=request(s,42);ev.qos=0;CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==1&&out[0].data==ERANGE);
  ev=request(s,42);ev.fflags|=0x80;CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==1&&out[0].data==ENOTSUP);
 }
 usleep(50000);CHECK(!calls[0]&&!calls[1]);
 __atomic_store_n(&pause_callbacks,1,__ATOMIC_RELEASE);
 for(unsigned s=0;s<2;s++){struct event ev=request(s,42);CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==0);}
 CHECK(wait_for(&blocked[0],1)&&wait_for(&blocked[1],1));
 for(unsigned round=0;round<100;round++)for(unsigned s=0;s<2;s++){
  states[s]=100+round;struct event ev=request(s,states[s]);ev.qos=0x1000;CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==0);
 }
 struct event remove=request(1,states[1]);remove.flags=EV_DELETE;remove.fflags=1;CHECK(call(ids[1],&remove,1,out,8,NULL,NULL,0x403)==0);
 CHECK(calls[0]==1&&calls[1]==1);__atomic_store_n(&pause_callbacks,0,__ATOMIC_RELEASE);
 CHECK(wait_for(&calls[0],2));usleep(50000);CHECK(calls[1]==1&&last_value[0]==199);
 for(unsigned round=0;round<32;round++){
  for(unsigned s=0;s<2;s++){
   states[s]=1000+round;struct event ev=request(s,states[s]);CHECK(call(ids[s],&ev,1,out,8,NULL,NULL,0x403)==0);
   char ch='a'+s;CHECK(write(pipes[s][1],&ch,1)==1);
  }
  CHECK(wait_for(&calls[0],3+round)&&wait_for(&calls[1],2+round)&&wait_for(&pipe_calls[0],1+round)&&wait_for(&pipe_calls[1],1+round));
 }
 for(unsigned s=0;s<2;s++){
  CHECK(wait_for(&running[s],0));struct event mixed[2]={request(s,0),{.ident=pipes[s][0],.filter=EVFILT_READ,.flags=EV_DELETE|EV_RECEIPT}};mixed[0].fflags&=~0x100;
  CHECK(call(ids[s],mixed,2,mixed,2,NULL,NULL,0x403)==2&&mixed[0].data==ESTALE&&mixed[1].data==0&&(mixed[0].flags&EV_ERROR)&&(mixed[1].flags&EV_ERROR));
  unsigned before=calls[s];remove=request(s,states[s]);remove.flags=EV_DELETE|EV_RECEIPT;remove.fflags=1;CHECK(call(ids[s],&remove,1,out,8,NULL,NULL,0x403)==1&&out[0].data==0);
  remove.flags=EV_DELETE;errno=0;CHECK(call(ids[s],&remove,1,NULL,0,NULL,NULL,0x403)==-1&&errno==ENOENT);usleep(20000);CHECK(calls[s]==before);
 }
 CHECK(!errors&&calls[0]==34&&calls[1]==33&&pipe_calls[0]==32&&pipe_calls[1]==32);
 puts("WORKLOOP_ASYNC_DEBOUNCE_COALESCING_DELETE_AND_REAL_SERIAL_CALLBACKS_OK domains=2 queued_updates=200 pipe=64");return 0;
}
