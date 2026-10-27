#include <assert.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
extern void abort_with_payload(unsigned int,unsigned long long,void*,unsigned int,const char*,unsigned long long);
static volatile sig_atomic_t segv_count,abrt_count;
static void handler(int signal){if(signal==SIGSEGV)segv_count++;else if(signal==SIGABRT)abrt_count++;}
struct result {int parent_segv,parent_abrt,sibling_segv,sibling_abrt,signaled_children;};
static void supervise(int output){
 assert(setsid()>0);struct sigaction action={0};action.sa_handler=handler;sigemptyset(&action.sa_mask);action.sa_flags=SA_RESTART;
 assert(!sigaction(SIGSEGV,&action,NULL)&&!sigaction(SIGABRT,&action,NULL));
 int finish[2],report[2];assert(!pipe(finish)&&!pipe(report));pid_t sibling=fork();assert(sibling>=0);
 if(!sibling){close(finish[1]);close(report[0]);char byte;assert(read(finish[0],&byte,1)==1);int counts[2]={segv_count,abrt_count};assert(write(report[1],counts,sizeof(counts))==sizeof(counts));_exit(0);}
 close(finish[0]);close(report[1]);struct result r={0};
 for(unsigned n=0;n<8;n++){
  pid_t victim=fork();assert(victim>=0);
  if(!victim){signal(SIGSEGV,SIG_DFL);signal(SIGABRT,SIG_DFL);struct rlimit limit={0,0};setrlimit(RLIMIT_CORE,&limit);
   if(n%2)abort_with_payload(1,n,NULL,0,"native fatal signal isolation fixture",0);
   else *(volatile uintptr_t*)8=1;
   _exit(99);
  }
  int status;assert(waitpid(victim,&status,0)==victim);assert(WIFSIGNALED(status));assert(WTERMSIG(status)==(n%2?SIGABRT:SIGSEGV));r.signaled_children++;
 }
 assert(write(finish[1],"x",1)==1);int counts[2];assert(read(report[0],counts,sizeof(counts))==sizeof(counts));int status;assert(waitpid(sibling,&status,0)==sibling&&WIFEXITED(status)&&!WEXITSTATUS(status));
 r.parent_segv=segv_count;r.parent_abrt=abrt_count;r.sibling_segv=counts[0];r.sibling_abrt=counts[1];assert(write(output,&r,sizeof(r))==sizeof(r));_exit(0);
}
int main(void){
 setbuf(stdout,NULL);int report[2];assert(!pipe(report));pid_t supervisor=fork();assert(supervisor>=0);if(!supervisor){close(report[0]);supervise(report[1]);}
 close(report[1]);struct result r;assert(read(report[0],&r,sizeof(r))==sizeof(r));int status;assert(waitpid(supervisor,&status,0)==supervisor&&WIFEXITED(status)&&!WEXITSTATUS(status));
 printf("NATIVE_FATAL_SIGNAL_CHILDREN=%d PARENT_SEGV=%d PARENT_ABRT=%d SIBLING_SEGV=%d SIBLING_ABRT=%d\n",r.signaled_children,r.parent_segv,r.parent_abrt,r.sibling_segv,r.sibling_abrt);
 if(r.parent_segv||r.parent_abrt||r.sibling_segv||r.sibling_abrt)return 2;
 puts("NATIVE_EIGHT_REAL_FATAL_CHILD_EXITS_PARENT_AND_SIBLING_SURVIVE_WITHOUT_GROUP_SIGNALS_OK");return 0;
}
