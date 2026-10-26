#include <dlfcn.h>
#include <errno.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/event.h>
#include <unistd.h>
#define CHECK(x) do {if(!(x)){printf("FAILED line=%d errno=%d %s\n",__LINE__,errno,#x);return 1;}}while(0)
struct qos_event {uint64_t ident;int16_t filter;uint16_t flags;int32_t qos;uint64_t udata;uint32_t fflags,xflags;int64_t data;uint64_t ext[4];};
struct message {mach_msg_header_t h;uint64_t payload;};
static int (*qevent)(int,const struct qos_event*,int,struct qos_event*,int,void*,unsigned long*,unsigned);
static int send_small(mach_port_t port,unsigned index){struct message m={.h={.msgh_bits=MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0),.msgh_size=sizeof(m),.msgh_remote_port=port,.msgh_id=1000+index},.payload=0xfedcba9800000000ull+index};return mach_msg(&m.h,MACH_SEND_MSG,sizeof(m),0,0,0,0);}
int main(void){
 setbuf(stdout,NULL);qevent=dlsym(RTLD_DEFAULT,"kevent_qos");CHECK(qevent);int kq=kqueue();CHECK(kq>=0);
 mach_port_t port;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&port)==0);CHECK(mach_port_insert_right(mach_task_self(),port,port,MACH_MSG_TYPE_MAKE_SEND)==0);
 struct qos_event change={.ident=port,.filter=EVFILT_MACHPORT,.flags=EV_ADD|EV_CLEAR,.udata=0x6789,.fflags=MACH_RCV_MSG|MACH_RCV_LARGE};struct qos_event event;
 CHECK(qevent(kq,&change,1,&event,1,NULL,NULL,3)==0);
 unsigned char guarded[288];unsigned char *buffer=guarded+16;unsigned copied=0;
 for(unsigned i=0;i<32;i++){
  CHECK(send_small(port,i)==0);memset(guarded,0xa5,sizeof guarded);unsigned long available=256;
  if(i==0){errno=0;CHECK(qevent(kq,NULL,0,&event,1,buffer,(void*)1,1)==-1&&errno==EFAULT);unsigned long small=8;errno=0;CHECK(qevent(kq,NULL,0,&event,1,buffer,&small,1)==-1&&errno==ENOTSUP);}
  int count=0;for(unsigned spin=0;!count;spin++){CHECK(spin<10000);available=256;count=qevent(kq,NULL,0,&event,1,buffer,&available,1|(i&1?8:0));CHECK(count>=0);if(!count)usleep(1000);}
  CHECK(count==1&&event.filter==EVFILT_MACHPORT&&event.ident==port&&event.udata==0x6789&&event.fflags==MACH_MSG_SUCCESS);
  CHECK(event.ext[1]>=sizeof(struct message)&&event.ext[1]<=64&&available==256-event.ext[1]);
  unsigned char *start=(void*)(uintptr_t)event.ext[0];CHECK(start==buffer+(i&1?available:0));struct message *m=(void*)start;CHECK(m->h.msgh_id==(int)(1000+i)&&m->payload==0xfedcba9800000000ull+i);
  for(unsigned j=0;j<16;j++)CHECK(guarded[j]==0xa5&&guarded[272+j]==0xa5);
  for(unsigned j=0;j<256;j++)if(buffer+j<start||buffer+j>=start+event.ext[1])CHECK(buffer[j]==0xa5);
  copied+=event.ext[1];
 }
 struct {mach_msg_header_t h;unsigned char payload[128];} big={.h={.msgh_bits=MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0),.msgh_size=sizeof(big),.msgh_remote_port=port,.msgh_id=2000}};memset(big.payload,0x5b,sizeof big.payload);CHECK(mach_msg(&big.h,MACH_SEND_MSG,sizeof(big),0,0,0,0)==0);
 unsigned long available=256;int count=0;for(unsigned spin=0;!count;spin++){CHECK(spin<10000);count=qevent(kq,NULL,0,&event,1,buffer,&available,1);CHECK(count>=0);if(!count)usleep(1000);}
 CHECK(event.fflags==MACH_RCV_TOO_LARGE&&available==256);
 unsigned char explicit_buffer[512];change.ext[0]=(uintptr_t)explicit_buffer;change.ext[1]=sizeof explicit_buffer;int registration=qevent(kq,&change,1,&event,1,NULL,NULL,3);printf("EXPLICIT_BUFFER_REGISTRATION rv=%d errno=%d flags=%x data=%lld fflags=%x\n",registration,errno,event.flags,(long long)event.data,event.fflags);CHECK(registration==0);
 count=0;for(unsigned spin=0;!count;spin++){CHECK(spin<10000);count=qevent(kq,NULL,0,&event,1,buffer,&available,1);CHECK(count>=0);if(!count)usleep(1000);}
 CHECK(event.fflags==MACH_MSG_SUCCESS&&event.ext[0]==(uintptr_t)explicit_buffer&&available==256);CHECK(((mach_msg_header_t*)explicit_buffer)->msgh_id==2000);CHECK(!memcmp(explicit_buffer+sizeof(mach_msg_header_t),big.payload,sizeof big.payload));
 printf("KEVENT_AUX_FRONT_STACK_BOUNDS_RESIDUAL_AND_LARGE_MESSAGE_RETRY_OK messages=33 copied=%u\n",copied);return 0;
}
