#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/event.h>
#include <unistd.h>
#ifndef EV_UDATA_SPECIFIC
#define EV_UDATA_SPECIFIC 0x100
#endif
#ifndef EV_DISPATCH2
#define EV_DISPATCH2 (EV_DISPATCH|EV_UDATA_SPECIFIC)
#endif
struct event {uint64_t ident;int16_t filter;uint16_t flags;int32_t qos;uint64_t udata;uint32_t fflags,xflags;int64_t data;uint64_t ext[4];};
static int (*call)(int,const struct event*,int,struct event*,int,void*,unsigned long*,unsigned);
static void fail(const char* text,int line){fprintf(stderr,"DISPATCH2_FAIL line=%d %s errno=%d\n",line,text,errno);exit(1);}
#define CHECK(x) do{if(!(x))fail(#x,__LINE__);}while(0)
static struct event ev(uint64_t id,int filter,unsigned flags,uint64_t udata,unsigned fflags){return(struct event){.ident=id,.filter=filter,.flags=flags,.qos=0x2000,.udata=udata,.fflags=fflags};}
static void change(int kq,struct event event,int expected){
 event.flags|=EV_RECEIPT;struct event result;
 CHECK(call(kq,&event,1,&result,1,NULL,NULL,3)==1);
 if(!(result.flags&EV_ERROR)||result.data!=expected)fprintf(stderr,"DISPATCH2_RECEIPT id=%llu filter=%d flags=%x udata=%llx actual=%lld expected=%d\n",(unsigned long long)event.ident,event.filter,event.flags,(unsigned long long)event.udata,(long long)result.data,expected);
 CHECK((result.flags&EV_ERROR)&&result.data==expected);
}
static int events(int kq,struct event* out,int count,int wait){return call(kq,NULL,0,out,count,NULL,NULL,wait?0:1);}
static void terminal(struct event* e,uint64_t tag){CHECK(e->udata==tag);CHECK((e->flags&(EV_DELETE|EV_ONESHOT|EV_DISPATCH2))==(EV_DELETE|EV_ONESHOT|EV_DISPATCH2));}
int main(void){
 alarm(40);setbuf(stdout,NULL);call=dlsym(RTLD_DEFAULT,"kevent_qos");CHECK(call);
 int kq=kqueue();CHECK(kq>=0);struct event out[8];
 /* Two independent registrations share one ident and filter. An in-flight
  * dispatch2 event must retain its registration until a real terminal ack. */
 for(unsigned round=0;round<1600;round++){
  for(unsigned tag=1;tag<=2;tag++)change(kq,ev(71,EVFILT_USER,EV_ADD|EV_CLEAR|EV_DISPATCH2,tag,0),0);
  for(unsigned tag=1;tag<=2;tag++)change(kq,ev(71,EVFILT_USER,EV_UDATA_SPECIFIC,tag,NOTE_TRIGGER),0);
  unsigned seen=0;
  while(seen!=6){int n=events(kq,out,8,1);CHECK(n>0);for(int i=0;i<n;i++){CHECK(out[i].filter==EVFILT_USER&&out[i].ident==71&&out[i].udata>=1&&out[i].udata<=2);unsigned bit=1u<<out[i].udata;CHECK(!(seen&bit));seen|=bit;}}
  for(unsigned tag=1;tag<=2;tag++)change(kq,ev(71,EVFILT_USER,EV_DELETE|EV_UDATA_SPECIFIC,tag,0),EINPROGRESS);
  CHECK(events(kq,out,8,0)==0);
  for(unsigned tag=1;tag<=2;tag++)change(kq,ev(71,EVFILT_USER,EV_ENABLE|EV_UDATA_SPECIFIC,tag,0),0);
  seen=0;
  while(seen!=6){int n=events(kq,out,8,1);CHECK(n>0);for(int i=0;i<n;i++){CHECK(out[i].udata>=1&&out[i].udata<=2);terminal(&out[i],out[i].udata);unsigned bit=1u<<out[i].udata;CHECK(!(seen&bit));seen|=bit;}}
  for(unsigned tag=1;tag<=2;tag++)change(kq,ev(71,EVFILT_USER,EV_DELETE|EV_ENABLE|EV_UDATA_SPECIFIC,tag,0),ENOENT);
 }
 puts("DISPATCH2_SPECIFIC_IDENTITIES_DEFERRED_DELETE_AND_3200_TERMINAL_ACKS_OK");
 char path[]="/private/tmp/dispatch2-vnode-XXXXXX";int fd=mkstemp(path);CHECK(fd>=0);
 unsigned interest=NOTE_WRITE|NOTE_DELETE|NOTE_RENAME;
 for(unsigned tag=1;tag<=2;tag++)change(kq,ev(fd,EVFILT_VNODE,EV_ADD|EV_CLEAR|EV_DISPATCH2,tag,interest),0);
 int other=open(path,O_RDONLY);CHECK(other>=0);close(other);
 CHECK(events(kq,out,8,0)==0);
 CHECK(write(fd,"a",1)==1);unsigned seen=0;
 while(seen!=6){int n=events(kq,out,8,1);CHECK(n>0);for(int i=0;i<n;i++){CHECK(out[i].filter==EVFILT_VNODE&&out[i].ident==(uint64_t)fd&&out[i].fflags==NOTE_WRITE);CHECK(out[i].udata>=1&&out[i].udata<=2);unsigned bit=1u<<out[i].udata;CHECK(!(seen&bit));seen|=bit;}}
 for(unsigned tag=1;tag<=2;tag++)change(kq,ev(fd,EVFILT_VNODE,EV_DELETE|EV_UDATA_SPECIFIC,tag,0),EINPROGRESS);
 change(kq,ev(fd,EVFILT_VNODE,EV_ENABLE|EV_UDATA_SPECIFIC,1,0),0);
 change(kq,ev(fd,EVFILT_VNODE,EV_DELETE|EV_ENABLE|EV_UDATA_SPECIFIC,2,0),0);
 CHECK(events(kq,out,8,1)==1);terminal(out,1);CHECK(events(kq,out,8,0)==0);close(fd);
 /* Closing the watched descriptor removes every tagged watcher and QoS row.
  * Reuse exceeds the metadata table size, catching stale-row accumulation. */
 for(unsigned round=0;round<1200;round++){
  fd=open(path,O_RDWR);CHECK(fd>=0);
  change(kq,ev(fd,EVFILT_VNODE,EV_ADD|EV_CLEAR|EV_DISPATCH2,round+100,interest),0);
  close(fd);CHECK(events(kq,out,8,0)==0);
 }
 unlink(path);close(kq);
 puts("VNODE_ACTUAL_FLAGS_OTHER_HANDLE_CLOSE_AND_1200_DESCRIPTOR_REUSE_CLEANUPS_OK");return 0;
}
