#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <mach/mach.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>
#define CHECK(x) do{if(!(x)){printf("ULOCK_FAILED line=%d errno=%d %s\n",__LINE__,errno,#x);return 1;}}while(0)
#define NOERRNO 0x1000000u
static int(*wait_on)(uint32_t,void*,uint64_t,uint32_t);static int(*wake)(uint32_t,void*,uint64_t);
static uint32_t word,operation;static unsigned entered,completed;static int returned[8];
static void* waiter(void* p){__atomic_add_fetch(&entered,1,__ATOMIC_RELEASE);int result;do{result=wait_on(NOERRNO|operation,&word,word,0);}while(result==-EINTR);unsigned index=__atomic_fetch_add(&completed,1,__ATOMIC_RELEASE);returned[(uintptr_t)p]=result;return 0;}
static int ready(pthread_t* threads,unsigned count){
 for(unsigned spin=0;spin<10000;spin++){
  int ready=__atomic_load_n(&entered,__ATOMIC_ACQUIRE)==count;
  for(unsigned i=0;ready&&i<count;i++){thread_basic_info_data_t info;mach_msg_type_number_t size=THREAD_BASIC_INFO_COUNT;ready=thread_info(pthread_mach_thread_np(threads[i]),THREAD_BASIC_INFO,(void*)&info,&size)==0&&info.run_state==TH_STATE_WAITING;}
  if(ready)return 1;usleep(1000);
 }
 return 0;
}
static int begin(pthread_t* threads,unsigned count,unsigned opcode){entered=completed=0;operation=opcode;word=pthread_mach_thread_np(pthread_self());for(uintptr_t i=0;i<count;i++){returned[i]=-999;if(pthread_create(&threads[i],NULL,waiter,(void*)i))return 0;}return ready(threads,count);}
static int done(unsigned target){for(unsigned i=0;i<10000;i++){if(__atomic_load_n(&completed,__ATOMIC_ACQUIRE)==target)return 1;usleep(1000);}return 0;}
int main(void){
 setbuf(stdout,NULL);wait_on=dlsym(RTLD_DEFAULT,"__ulock_wait");wake=dlsym(RTLD_DEFAULT,"__ulock_wake");CHECK(wait_on&&wake);word=0x1234;
 CHECK(wait_on(NOERRNO|1,&word,word+1,0)==0);CHECK(wait_on(NOERRNO|2,&word,word+1,0)==0);errno=73;CHECK(wait_on(NOERRNO|1,NULL,0,1)==-EINVAL&&errno==73);CHECK(wait_on(NOERRNO|1,(void*)1,0,1)==-EINVAL&&errno==73);CHECK(wait_on(NOERRNO|1,(void*)8,0,1)==-EFAULT&&errno==73);CHECK(wait_on(NOERRNO|1,&word,word,1000)==-ETIMEDOUT&&errno==73);
 errno=0;CHECK(open("/private/tmp/linuxcode-ulock-file-does-not-exist",O_RDONLY)==-1&&errno==ENOENT);char ch;errno=0;CHECK(read(-1,&ch,1)==-1&&errno==EBADF);
 pthread_t threads[8];CHECK(begin(threads,1,2));CHECK(wait_on(NOERRNO|1,&word,word,1000)==-EDOM);CHECK(wake(NOERRNO|2|0x400,&word,0)==0);CHECK(pthread_join(threads[0],NULL)==0&&returned[0]==0);
 CHECK(begin(threads,8,2));
 for(unsigned i=0;i<8;i++){CHECK(wake(NOERRNO|2|0x400,&word,0)==0);CHECK(done(i+1));}
 for(unsigned i=0;i<8;i++)CHECK(pthread_join(threads[i],NULL)==0);
 unsigned seen=0;for(unsigned i=0;i<8;i++){CHECK(returned[i]>=0&&returned[i]<8);seen|=1u<<returned[i];}CHECK(seen==255);
 CHECK(begin(threads,8,1));CHECK(wake(NOERRNO|1|0x100,&word,0)==0);for(unsigned i=0;i<8;i++)CHECK(pthread_join(threads[i],NULL)==0);seen=0;for(unsigned i=0;i<8;i++){CHECK(returned[i]>=0&&returned[i]<8);seen|=1u<<returned[i];}CHECK(seen==255);
 CHECK(begin(threads,1,2));pid_t child=fork();CHECK(child>=0);
 if(!child){int result=wait_on(NOERRNO|2,&word,word+1,0);_exit(result==0?0:17);}
 int status;CHECK(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);CHECK(wake(NOERRNO|2|0x400,&word,0)==0);CHECK(pthread_join(threads[0],NULL)==0&&returned[0]==0);
 puts("ULOCK_REAL_SINGLE_AND_MULTIPLE_WAITER_COUNTS_TIMEOUT_ERRORS_AND_FORK_OK waiters=8");return 0;
}
