#define _GNU_SOURCE
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <errno.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <unistd.h>
#define LINUX_SYSCALL(...) ({long _rv=syscall(__VA_ARGS__);_rv<0?-errno:_rv;})
#define FUTEX_WAIT 0
#define FUTEX_WAKE 1
static int __linux_futex(int* p,int op,int v,const struct timespec* t,int* p2,int v2){return syscall(SYS_futex,p,op,v,t,p2,v2);}
static int __linux_futex_reterr(int* p,int op,int v,const struct timespec* t,int* p2,int v2){long r=syscall(SYS_futex,p,op,v,t,p2,v2);return r<0?-errno:r;}
#include "semaphore.inc"
static int request,reply;static atomic_int failed;static unsigned count=50000;static pthread_t waiterThread;
static void* pong(void* unused){for(unsigned i=0;i<count;++i){if(!sem_down(&request,1)){atomic_store(&failed,1);sem_up(&reply);return NULL;}sem_up(&reply);}return NULL;}
static void nothing(int sig){}
static pthread_barrier_t barrier;
static void* manyWaiters(void* unused){pthread_barrier_wait(&barrier);if(!sem_down(&request,1))atomic_store(&failed,1);return NULL;}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void* repeatedInterrupts(void* unused){for(unsigned i=0;i<12;++i){usleep(50000);pthread_kill(waiterThread,SIGUSR1);}return NULL;}

static void* interrupt(void* unused){usleep(50000);pthread_kill(waiterThread,SIGUSR1);usleep(50000);sem_up(&request);return NULL;}
int main(void){setbuf(stdout,NULL);signal(SIGUSR1,nothing);waiterThread=pthread_self();
 pthread_t thread;pthread_create(&thread,NULL,pong,NULL);unsigned done=0;
 for(;done<count;++done){sem_up(&request);if(!sem_down(&reply,1)||atomic_load(&failed))break;}
 pthread_join(thread,NULL);printf("WORKQUEUE_PINGPONG completed=%u failed=%d request=%d reply=%d\n",done,atomic_load(&failed),request,reply);
 if(done!=count||atomic_load(&failed))return 12;
 request=0;pthread_create(&thread,NULL,interrupt,NULL);int result=sem_down(&request,1);pthread_join(thread,NULL);printf("WORKQUEUE_INTERRUPTED_WAIT result=%d remaining=%d\n",result,request);
 if(result!=1||request!=0)return 13;
 for(unsigned cycle=0;cycle<32;++cycle){
  pthread_t threads[16];request=0;atomic_store(&failed,0);pthread_barrier_init(&barrier,NULL,17);
  for(unsigned i=0;i<16;++i)pthread_create(&threads[i],NULL,manyWaiters,NULL);
  pthread_barrier_wait(&barrier);usleep(10000);
  for(unsigned i=0;i<16;++i)sem_up(&request);
  for(unsigned i=0;i<16;++i)pthread_join(threads[i],NULL);
  pthread_barrier_destroy(&barrier);
  if(atomic_load(&failed)||request!=0){printf("WORKQUEUE_MULTIWAITER_FAILED cycle=%u count=%d\n",cycle,request);return 14;}
 }
 printf("WORKQUEUE_MULTIWAITER_OK waits=512\n");
 request=0;if(sem_down(&request,0)!=0)return 15;
 pthread_create(&thread,NULL,repeatedInterrupts,NULL);double started=now();result=sem_down(&request,1);double elapsed=now()-started;pthread_join(thread,NULL);
 printf("WORKQUEUE_MONOTONIC_TIMEOUT result=%d elapsed_ms=%.1f\n",result,elapsed*1000);
 if(result!=0||elapsed<0.8||elapsed>2.0)return 16;
 printf("WORKQUEUE_SEMAPHORE_CREDITS_AND_INTERRUPTION_OK iterations=%u\n",count);return 0;
}
