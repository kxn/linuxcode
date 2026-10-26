#include <dlfcn.h>
#include <mach/mach.h>
#include <mach-o/loader.h>
#include <servers/bootstrap.h>
#include <spawn.h>
#include <sys/wait.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#define CHECK(x) do{if(!(x)){printf("FAILED pid=%d line=%d %s\n",getpid(),__LINE__,#x);return 1;}}while(0)
struct recipe{uint32_t key,command,previous,size;};
struct proc_info{uint64_t unique_pid;int32_t pid;uint32_t flags,pidversion,persona,uid,gid;uint8_t uuid[16];};
struct token{struct proc_info originator,proximate;};
struct packet{mach_msg_header_t h;audit_token_t audit;uint8_t uuid[16];uint32_t sequence;};
union incoming{struct packet p;unsigned char bytes[2048];};
typedef kern_return_t(*create_t)(mach_port_t,unsigned char*,unsigned,mach_port_t*);
typedef kern_return_t(*command_t)(mach_port_t,unsigned,unsigned,unsigned char*,unsigned,unsigned char*,unsigned*);
extern char** environ;extern const struct mach_header_64 _mh_execute_header;
static int own_uuid(uint8_t out[16]){const struct mach_header_64* h=&_mh_execute_header;const unsigned char* at=(void*)(h+1);for(unsigned i=0;i<h->ncmds;i++){const struct load_command* c=(void*)at;if(c->cmd==LC_UUID&&c->cmdsize==sizeof(struct uuid_command)){memcpy(out,((const struct uuid_command*)c)->uuid,16);return 1;}at+=c->cmdsize;}return 0;}
static int child(const char* name){
 mach_port_t service=0,reply=0;CHECK(bootstrap_look_up(bootstrap_port,name,&service)==0);CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&reply)==0);
 create_t create=dlsym(RTLD_DEFAULT,"host_create_mach_voucher");CHECK(create);struct recipe r={3,610,0,0};mach_port_t voucher=0;CHECK(create(mach_host_self(),(void*)&r,sizeof r,&voucher)==0&&voucher);
 audit_token_t audit;mach_msg_type_number_t count=sizeof audit/sizeof(natural_t);CHECK(task_info(mach_task_self(),TASK_AUDIT_TOKEN,(void*)&audit,&count)==0);uint8_t uuid[16];CHECK(own_uuid(uuid));
 for(unsigned i=0;i<32;i++){
  struct packet p={.h={.msgh_bits=MACH_MSGH_BITS_SET(MACH_MSG_TYPE_COPY_SEND,MACH_MSG_TYPE_MAKE_SEND_ONCE,MACH_MSG_TYPE_COPY_SEND,0),.msgh_size=sizeof p,.msgh_remote_port=service,.msgh_local_port=reply,.msgh_voucher_port=voucher,.msgh_id=6000+i},.audit=audit,.sequence=i};memcpy(p.uuid,uuid,16);
  CHECK(mach_msg(&p.h,MACH_SEND_MSG,sizeof p,0,0,0,0)==0);union incoming ack={0};CHECK(mach_msg(&ack.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof ack,reply,10000,0)==0&&ack.p.h.msgh_id==(int)(7000+i));
 }
 CHECK(mach_port_deallocate(mach_task_self(),voucher)==0);puts("BANK_CROSS_PROCESS_CHILD_SENT_REAL_VOUCHERS");return 0;
}
int main(int argc,char** argv){
 setbuf(stdout,NULL);if(argc==3&&!strcmp(argv[1],"--child"))return child(argv[2]);
 command_t command=dlsym(RTLD_DEFAULT,"mach_voucher_attr_command");CHECK(command);mach_port_t receiver=0;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&receiver)==0);CHECK(mach_port_insert_right(mach_task_self(),receiver,receiver,MACH_MSG_TYPE_MAKE_SEND)==0);
 char name[128];snprintf(name,sizeof name,"org.linuxcode.bank-voucher-%d",getpid());CHECK(bootstrap_register(bootstrap_port,name,receiver)==0);
 char* child_argv[]={argv[0],"--child",name,NULL};pid_t pid;CHECK(posix_spawn(&pid,argv[0],NULL,NULL,child_argv,environ)==0);
 uint64_t generation=0;
 for(unsigned i=0;i<32;i++){
  union incoming in={0};CHECK(mach_msg(&in.p.h,MACH_RCV_MSG|MACH_RCV_VOUCHER|MACH_RCV_TIMEOUT,0,sizeof in,receiver,15000,0)==0);CHECK(in.p.h.msgh_id==(int)(6000+i)&&in.p.h.msgh_voucher_port&&in.p.sequence==i&&in.p.audit.val[5]==pid);
  struct token identity={0};unsigned count=sizeof identity;CHECK(command(in.p.h.msgh_voucher_port,3,2,NULL,0,(void*)&identity,&count)==0&&count==sizeof identity);
  struct proc_info* source=&identity.originator;struct proc_info* proximate=&identity.proximate;
  CHECK(source->pid==pid&&proximate->pid==pid&&source->unique_pid&&source->unique_pid==proximate->unique_pid);
  CHECK(source->pidversion==in.p.audit.val[7]&&source->uid==in.p.audit.val[1]&&source->gid==in.p.audit.val[2]);
  CHECK(proximate->pidversion==source->pidversion&&proximate->uid==source->uid&&proximate->gid==source->gid);
  CHECK(!memcmp(source->uuid,in.p.uuid,16)&&!memcmp(proximate->uuid,in.p.uuid,16));
  if(i)CHECK(source->unique_pid==generation);else generation=source->unique_pid;
  CHECK(mach_port_deallocate(mach_task_self(),in.p.h.msgh_voucher_port)==0);
  mach_msg_header_t ack={.msgh_bits=MACH_MSGH_BITS(MACH_MSG_TYPE_MOVE_SEND_ONCE,0),.msgh_size=sizeof ack,.msgh_remote_port=in.p.h.msgh_remote_port,.msgh_id=7000+i};CHECK(mach_msg(&ack,MACH_SEND_MSG,sizeof ack,0,0,0,0)==0);
 }
 int status;CHECK(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0);CHECK(mach_port_destroy(mach_task_self(),receiver)==0);
 printf("BANK_REAL_CROSS_PROCESS_ORIGINATOR_AUDIT_GENERATION_AND_UUID_OK messages=32 child=%d\n",pid);return 0;
}
