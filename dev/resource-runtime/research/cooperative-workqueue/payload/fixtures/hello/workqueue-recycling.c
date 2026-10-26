#include <dispatch/dispatch.h>
#include <stdio.h>
#include <unistd.h>
static unsigned completed;
static void work(void* unused){usleep(100);__atomic_fetch_add(&completed,1,__ATOMIC_RELAXED);}
static int burst(unsigned cycles,unsigned count){
 dispatch_group_t group=dispatch_group_create();dispatch_queue_t queue=dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT,0);
 for(unsigned i=0;i<cycles;++i){
  for(unsigned j=0;j<count;++j)dispatch_group_async_f(group,queue,NULL,work);
  if(dispatch_group_wait(group,dispatch_time(DISPATCH_TIME_NOW,30LL*NSEC_PER_SEC))){printf("WORKQUEUE_RECYCLING_TIMEOUT cycle=%u completed=%u\n",i,completed);return 12;}
  usleep(1000);
 }
 dispatch_release(group);return 0;
}
int main(void){setbuf(stdout,NULL);int status=burst(128,64);if(status)return status;
 printf("WORKQUEUE_RECYCLING_BURSTS_OK %u\n",completed);sleep(17);
 status=burst(16,64);if(status)return status;
 if(completed!=9216){printf("WORKQUEUE_RECYCLING_COUNT_MISMATCH %u\n",completed);return 15;}
 printf("WORKQUEUE_RECYCLING_AND_IDLE_EXPIRY_OK callbacks=%u\n",completed);return 0;
}
