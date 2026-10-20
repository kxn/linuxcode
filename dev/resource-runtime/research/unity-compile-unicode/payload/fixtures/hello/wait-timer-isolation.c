#include <mach/mach.h>
#include <mach/semaphore.h>
#include <pthread.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
static semaphore_t first,second;
static int workerError;
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){printf("WAIT_TIMER_CHECK_FAILED line=%d %s\n",__LINE__,#x);return 11;}}while(0)
static void* signaler(void* unused){
 usleep(100000);if(semaphore_signal(first)!=KERN_SUCCESS)workerError=1;
 usleep(800000);if(semaphore_signal(second)!=KERN_SUCCESS)workerError=2;return NULL;
}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(void){setbuf(stdout,NULL);semaphore_t control;
 CHECK(semaphore_create(mach_task_self(),&control,SYNC_POLICY_FIFO,0)==KERN_SUCCESS);
 mach_timespec_t shortWait={0,30000000};CHECK(semaphore_timedwait(control,shortWait)==KERN_OPERATION_TIMED_OUT);
 CHECK(semaphore_destroy(mach_task_self(),control)==KERN_SUCCESS);
 for(int trial=0;trial<4;++trial){
  CHECK(semaphore_create(mach_task_self(),&first,SYNC_POLICY_FIFO,0)==KERN_SUCCESS);
  CHECK(semaphore_create(mach_task_self(),&second,SYNC_POLICY_FIFO,0)==KERN_SUCCESS);
  pthread_t t;workerError=0;CHECK(pthread_create(&t,NULL,signaler,NULL)==0);
  mach_timespec_t early={0,500000000};kern_return_t a=semaphore_timedwait(first,early);
  double begin=now();kern_return_t b=semaphore_wait(second);double elapsed=now()-begin;
  CHECK(pthread_join(t,NULL)==0);CHECK(workerError==0);
  printf("WAIT_TIMER_TRIAL %d first=%d second=%d elapsed_ms=%.1f\n",trial,a,b,elapsed*1000);
  CHECK(semaphore_destroy(mach_task_self(),first)==KERN_SUCCESS);CHECK(semaphore_destroy(mach_task_self(),second)==KERN_SUCCESS);
  CHECK(a==KERN_SUCCESS);
  if(b!=KERN_SUCCESS){printf("WAIT_TIMER_LEAKED_TO_INDEFINITE_WAIT status=%d\n",b);return 12;}
  CHECK(elapsed>=0.55);
 }
 printf("WAIT_TIMER_DEADLINE_CANCELLATION_ISOLATION_OK checks=%u\n",checks);return 0;
}
