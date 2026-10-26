#include <dlfcn.h>
#include <mach/mach.h>
#include <pthread.h>
#include <servers/bootstrap.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#define CHECK(x) do{checks++;if(!(x)){printf("MSG2_AUX_FAILED pid=%d line=%d %s\n",getpid(),__LINE__,#x);return 1;}}while(0)
#define VECTOR (1ull<<32)
#define MQ (1ull<<34)
struct vector{uint64_t data,rcv;uint32_t send_size,rcv_size;};
struct packet{mach_msg_header_t h;uint32_t sequence,value;};
union incoming{struct packet p;unsigned char bytes[512];};
typedef mach_msg_return_t(*msg2_t)(void*,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
static msg2_t msg2;static unsigned checks;extern char** environ;
static uint64_t pack(uint32_t low,uint32_t high){return low|((uint64_t)high<<32);}
static void pattern(unsigned char* bytes,unsigned size,unsigned seed){memset(bytes,0xee,8);for(unsigned i=8;i<size;i++)bytes[i]=(seed+7*i)&255;}
static int content(const unsigned char* bytes,unsigned size,unsigned seed){uint32_t header[2];memcpy(header,bytes,8);if(header[0]!=size||header[1])return 0;for(unsigned i=8;i<size;i++)if(bytes[i]!=((seed+7*i)&255))return 0;return 1;}
static mach_msg_return_t send_aux(mach_port_t port,mach_port_t reply,unsigned sequence,const void* aux,unsigned size){struct packet p={.sequence=sequence,.value=0x12345678};struct vector vectors[2]={{.data=(uintptr_t)&p,.send_size=sizeof p},{.data=(uintptr_t)aux,.send_size=size}};return msg2(vectors,VECTOR|MQ|MACH_SEND_MSG,pack(MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,reply?MACH_MSG_TYPE_MAKE_SEND_ONCE:0),2),pack(port,reply),pack(0,10000+sequence),0,0,0);}
static mach_msg_return_t receive_aux(mach_port_t port,union incoming* p,void* aux,unsigned size,unsigned extra){struct vector v[2]={{.data=(uintptr_t)p,.rcv_size=sizeof *p},{.data=(uintptr_t)aux,.rcv_size=size}};return msg2(v,VECTOR|MACH_RCV_MSG|MACH_RCV_TIMEOUT|extra,0,0,0,pack(0,port),2,5000);}
static int make_port(mach_port_t* p){return mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,p)==0&&mach_port_insert_right(mach_task_self(),*p,*p,MACH_MSG_TYPE_MAKE_SEND)==0;}
static int child(const char* name){mach_port_t service=0,reply=0;CHECK(bootstrap_look_up(bootstrap_port,name,&service)==0&&make_port(&reply));unsigned char aux[40];for(unsigned i=0;i<64;i++){pattern(aux,sizeof aux,i);CHECK(send_aux(service,reply,i,aux,sizeof aux)==0);union incoming ack={0};CHECK(mach_msg(&ack.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof ack,reply,10000,0)==0&&ack.p.h.msgh_id==(int)(20000+i));}CHECK(mach_port_destroy(mach_task_self(),reply)==0);return 0;}
static mach_port_t waiting_port;static unsigned receiver_started;
static void* waiting_receiver(void* unused){union incoming p={0};unsigned char aux[1024];__atomic_store_n(&receiver_started,1,__ATOMIC_RELEASE);if(receive_aux(waiting_port,&p,aux,sizeof aux,0)!=0||p.p.sequence!=77||!content(aux,40,77))return (void*)1;return 0;}
int main(int argc,char** argv){
 setbuf(stdout,NULL);msg2=dlsym(RTLD_DEFAULT,"mach_msg2_internal");CHECK(msg2);if(argc==3&&!strcmp(argv[1],"--child"))return child(argv[2]);
 mach_port_t port=0;CHECK(make_port(&port));unsigned char sent[1024],received[1056];union incoming p={0};unsigned sizes[]={8,40,128,1024};
 for(unsigned i=0;i<4;i++){unsigned size=sizes[i];pattern(sent,size,i);memset(received,0xa5,sizeof received);CHECK(send_aux(port,0,i,sent,size)==0);CHECK(receive_aux(port,&p,received,sizeof received,0)==0&&p.p.sequence==i&&p.p.h.msgh_id==(int)(10000+i)&&content(received,size,i));CHECK(sent[0]==0xee&&sent[7]==0xee);for(unsigned j=size;j<sizeof received;j++)CHECK(received[j]==0xa5);}
 unsigned char* readonly=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_ANON|MAP_PRIVATE,-1,0);CHECK(readonly!=MAP_FAILED);pattern(readonly,40,12);CHECK(mprotect(readonly,4096,PROT_READ)==0);CHECK(send_aux(port,0,12,readonly,40)==0&&receive_aux(port,&p,received,sizeof received,0)==0&&content(received,40,12));CHECK(munmap(readonly,4096)==0);
 /* Auxiliary overflow must retain the actual queued message for retry. */
 pattern(sent,40,13);CHECK(send_aux(port,0,13,sent,40)==0);memset(received,0xa5,sizeof received);CHECK(receive_aux(port,&p,received,8,MACH_RCV_LARGE|MACH_RCV_LARGE_IDENTITY)==MACH_RCV_TOO_LARGE);CHECK(*(uint32_t*)received==40&&received[4]==0xa5&&p.p.h.msgh_size==sizeof(struct packet)&&p.p.h.msgh_local_port==port);CHECK(receive_aux(port,&p,received,sizeof received,0)==0&&p.p.sequence==13&&content(received,40,13));
 pattern(sent,40,14);CHECK(send_aux(port,0,14,sent,40)==0);struct vector one={.data=(uintptr_t)&p,.rcv_size=sizeof p};CHECK(msg2(&one,VECTOR|MACH_RCV_MSG|MACH_RCV_TIMEOUT|MACH_RCV_LARGE,0,0,0,pack(0,port),1,1000)==MACH_RCV_TOO_LARGE);CHECK(receive_aux(port,&p,received,sizeof received,0)==0&&p.p.sequence==14&&content(received,40,14));
 CHECK(send_aux(port,0,15,sent,7)==0x10000018);CHECK(send_aux(port,0,15,sent,1025)==0x10000019);CHECK(send_aux(port,0,15,NULL,40)==MACH_SEND_INVALID_DATA);CHECK(send_aux(port,0,15,(void*)1,40)==MACH_SEND_INVALID_DATA);CHECK(mach_msg(&p.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof p,port,1,0)==MACH_RCV_TIMED_OUT);
 pattern(sent,40,16);CHECK(send_aux(port,0,16,sent,40)==0);CHECK(receive_aux(port,&p,(void*)1,40,0)==MACH_RCV_INVALID_DATA);CHECK(mach_msg(&p.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof p,port,1,0)==MACH_RCV_TIMED_OUT);
 /* The legacy receive API deliberately omits aux data for compatibility. */
 CHECK(send_aux(port,0,17,sent,40)==0);CHECK(mach_msg(&p.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof p,port,1000,0)==0&&p.p.sequence==17);
 waiting_port=port;pthread_t thread;CHECK(pthread_create(&thread,NULL,waiting_receiver,NULL)==0);while(!__atomic_load_n(&receiver_started,__ATOMIC_ACQUIRE))usleep(1000);usleep(20000);pattern(sent,40,77);CHECK(send_aux(port,0,77,sent,40)==0);void* thread_status;CHECK(pthread_join(thread,&thread_status)==0&&!thread_status);
 /* Destroy queued sidecars and their actual port/message lifetimes. */
 for(unsigned round=0;round<16;round++){mach_port_t doomed=0;CHECK(make_port(&doomed));for(unsigned n=0;n<4;n++)CHECK(send_aux(doomed,0,n,sent,1024)==0);CHECK(mach_port_destroy(mach_task_self(),doomed)==0);}
 char name[128];snprintf(name,sizeof name,"org.linuxcode.msg2-aux-%d",getpid());CHECK(bootstrap_register(bootstrap_port,name,port)==0);char* child_args[]={argv[0],"--child",name,NULL};pid_t pid;CHECK(posix_spawn(&pid,argv[0],NULL,NULL,child_args,environ)==0);
 for(unsigned i=0;i<64;i++){memset(received,0xa5,sizeof received);CHECK(receive_aux(port,&p,received,sizeof received,0)==0&&p.p.sequence==i&&p.p.h.msgh_id==(int)(10000+i)&&content(received,40,i));CHECK(received[40]==0xa5);mach_msg_header_t ack={.msgh_bits=MACH_MSGH_BITS(MACH_MSG_TYPE_MOVE_SEND_ONCE,0),.msgh_size=sizeof ack,.msgh_remote_port=p.p.h.msgh_remote_port,.msgh_id=20000+i};CHECK(mach_msg(&ack,MACH_SEND_MSG,sizeof ack,0,0,0,0)==0);}
 int status;CHECK(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0);CHECK(mach_port_destroy(mach_task_self(),port)==0);
 printf("MSG2_AUX_REAL_BYTES_CROSS_PROCESS_RETRY_AND_LIFETIMES_OK checks=%u child_messages=64 queued_destructions=64 max_aux=1024\n",checks);return 0;
}
