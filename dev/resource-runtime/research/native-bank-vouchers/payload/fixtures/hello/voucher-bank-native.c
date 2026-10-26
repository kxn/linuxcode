#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_host.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include <string.h>
#include <unistd.h>
#define CHECK(x) do{if(!(x)){printf("FAILED line=%d %s\n",__LINE__,#x);return 1;}}while(0)
struct recipe{uint32_t key,command,previous,size;};
struct proc_info{uint64_t unique_pid;int32_t pid;uint32_t flags,pidversion,persona,uid,gid;uint8_t uuid[16];};
struct token{struct proc_info originator,proximate;};
typedef kern_return_t(*create_t)(mach_port_t,unsigned char*,unsigned,mach_port_t*);
typedef kern_return_t(*command_t)(mach_port_t,unsigned,unsigned,unsigned char*,unsigned,unsigned char*,unsigned*);
static unsigned worker_ready;
static mach_port_t other_thread;
static int stop_pipe[2];
static void* waiting_thread(void* unused){other_thread=pthread_mach_thread_np(pthread_self());__atomic_store_n(&worker_ready,1,__ATOMIC_RELEASE);char byte;read(stop_pipe[0],&byte,1);return NULL;}
int main(void){
 setbuf(stdout,NULL);create_t create=dlsym(RTLD_DEFAULT,"host_create_mach_voucher");command_t command=dlsym(RTLD_DEFAULT,"mach_voucher_attr_command");CHECK(create&&command);
 host_t host=mach_host_self();struct recipe r={3,610,0,0};mach_port_t voucher=0;
 CHECK(create(host,(void*)&r,sizeof r,&voucher)==0&&voucher);mach_port_type_t type=0;CHECK(mach_port_type(mach_task_self(),voucher,&type)==0&&(type&MACH_PORT_TYPE_SEND));
 int32_t pid=0;unsigned size=sizeof pid;CHECK(command(voucher,3,1,NULL,0,(void*)&pid,&size)==0&&size==sizeof pid&&pid==getpid());
 /* Apple's BANK_PERSONA_TOKEN applies to an account linking tasks; a plain
  * task-default value must reject it rather than invent an account identity. */
 struct token identity={0};size=sizeof identity;CHECK(command(voucher,3,2,NULL,0,(void*)&identity,&size)==KERN_INVALID_OBJECT);
 audit_token_t audit;mach_msg_type_number_t count=sizeof audit/sizeof(natural_t);CHECK(task_info(mach_task_self(),TASK_AUDIT_TOKEN,(task_info_t)&audit,&count)==0&&audit.val[5]==getpid());
 uint32_t persona=0;size=sizeof persona;CHECK(command(voucher,3,3,NULL,0,(void*)&persona,&size)==0&&persona==UINT32_MAX);
 puts("BANK_PHASE_TASK_IDENTITY_OK");
 size=1;CHECK(command(voucher,3,1,NULL,0,(void*)&pid,&size)==KERN_NO_SPACE);
 mach_port_t concrete=0;r=(struct recipe){3,5,voucher,0};CHECK(create(host,(void*)&r,sizeof r,&concrete)==0&&concrete);
 struct{struct recipe r;struct{uint32_t persona,padding;uint64_t unique_pid;} body;} change={.r={3,611,concrete,16},.body={.persona=123456,.unique_pid=0}};
 mach_port_t altered=0;CHECK(create(host,(void*)&change,sizeof change,&altered)==KERN_NO_ACCESS&&!altered);
 CHECK(pipe(stop_pipe)==0);pthread_t waiting;CHECK(pthread_create(&waiting,NULL,waiting_thread,NULL)==0);
 for(unsigned spin=0;!__atomic_load_n(&worker_ready,__ATOMIC_ACQUIRE);spin++){CHECK(spin<10000);usleep(1000);}
 CHECK(thread_set_mach_voucher(other_thread,concrete)==KERN_INVALID_ARGUMENT);CHECK(write(stop_pipe[1],"x",1)==1);CHECK(pthread_join(waiting,NULL)==0);close(stop_pipe[0]);close(stop_pipe[1]);
 puts("BANK_PHASE_BEFORE_THREAD_VOUCHER");
 CHECK(thread_set_mach_voucher(mach_thread_self(),concrete)==0);mach_port_t selected=0;CHECK(thread_get_mach_voucher(mach_thread_self(),0,&selected)==0&&selected);CHECK(mach_port_deallocate(mach_task_self(),selected)==0);CHECK(thread_set_mach_voucher(mach_thread_self(),MACH_PORT_NULL)==0);
 puts("BANK_PHASE_THREAD_VOUCHER_OK");
 for(unsigned i=0;i<128;i++){mach_port_t copy=0;r=(struct recipe){3,1,concrete,0};CHECK(create(host,(void*)&r,sizeof r,&copy)==0&&copy);size=sizeof pid;CHECK(command(copy,3,1,NULL,0,(void*)&pid,&size)==0&&pid==getpid());CHECK(mach_port_deallocate(mach_task_self(),copy)==0);}
 puts("BANK_PHASE_COPY_RELEASE_OK");
 mach_port_t port=0;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&port)==0);CHECK(mach_port_insert_right(mach_task_self(),port,port,MACH_MSG_TYPE_MAKE_SEND)==0);
 puts("BANK_PHASE_BEFORE_MESSAGE_TRANSFER");
 for(unsigned i=0;i<32;i++){
  struct {mach_msg_header_t h;uint32_t sequence;} out={.h={.msgh_bits=MACH_MSGH_BITS_SET(MACH_MSG_TYPE_COPY_SEND,0,MACH_MSG_TYPE_COPY_SEND,0),.msgh_size=sizeof out,.msgh_remote_port=port,.msgh_voucher_port=concrete,.msgh_id=4000+i},.sequence=i};
  CHECK(mach_msg(&out.h,MACH_SEND_MSG,sizeof out,0,0,0,0)==0);
  union{mach_msg_header_t h;unsigned char bytes[1024];} in={0};CHECK(mach_msg(&in.h,MACH_RCV_MSG|MACH_RCV_VOUCHER|MACH_RCV_TIMEOUT,0,sizeof in,port,1000,0)==0);
  CHECK(in.h.msgh_id==(int)(4000+i)&&in.h.msgh_voucher_port);size=sizeof pid;CHECK(command(in.h.msgh_voucher_port,3,1,NULL,0,(void*)&pid,&size)==0&&pid==getpid());CHECK(mach_port_deallocate(mach_task_self(),in.h.msgh_voucher_port)==0);
 }
 CHECK(mach_port_deallocate(mach_task_self(),concrete)==0);CHECK(mach_port_deallocate(mach_task_self(),voucher)==0);
 printf("BANK_REAL_PORT_IDENTITY_COPY_THREAD_AND_MESSAGE_LIFETIMES_OK pid=%d copies=128 messages=32\n",getpid());return 0;
}
