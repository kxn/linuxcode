#include <mach/mach.h>
#include <mach/mach_time.h>
#include <mach/mach_eventlink.h>
#include <mach/mach_eventlink_types.h>
#include <pthread.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#define CHECK(x) do {if(!(x)){printf("failed line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static eventlink_port_pair_t pair;
static uint64_t ticks(uint64_t ns) {mach_timebase_info_data_t t;mach_timebase_info(&t);return ns*t.denom/t.numer;}
static void* peer(void* ignored) {
    usleep(20000);
    if(mach_eventlink_signal(pair[1],0)!=KERN_SUCCESS)return (void*)1;
    uint64_t count=0;
    kern_return_t kr=mach_eventlink_wait_until(pair[1],&count,MELSW_OPTION_NONE,KERN_CLOCK_MACH_ABSOLUTE_TIME,mach_absolute_time()+ticks(2000000000));
    if(kr || count!=1)return (void*)2;
    if(mach_eventlink_signal(pair[1],0)!=KERN_SUCCESS)return (void*)3;
    return 0;
}
int main(void) {
    setbuf(stdout,0);
    uint64_t large=UINT64_C(1)<<40;
    CHECK(mach_eventlink_wait_until(MACH_PORT_NULL,&large,MELSW_OPTION_NO_WAIT,0,0)==KERN_INVALID_ARGUMENT);CHECK(large==(UINT64_C(1)<<40));
    CHECK(mach_eventlink_signal(MACH_PORT_NULL,0)!=KERN_SUCCESS);
    CHECK(mach_eventlink_create(mach_task_self(),MELC_OPTION_NONE,pair)==KERN_INVALID_ARGUMENT);
    CHECK(mach_eventlink_create(mach_task_self(),MELC_OPTION_NO_COPYIN,pair)==KERN_SUCCESS);CHECK(pair[0] && pair[1] && pair[0]!=pair[1]);puts("EVENTLINK_CREATED");
    uint64_t count=0;
    CHECK(mach_eventlink_wait_until(pair[0],&count,MELSW_OPTION_NO_WAIT,KERN_CLOCK_MACH_ABSOLUTE_TIME,0)==KERN_INVALID_ARGUMENT);
    mach_port_t thread=mach_thread_self();CHECK(mach_eventlink_associate(pair[0],thread,0,0,0,0,MELA_OPTION_NONE)==KERN_SUCCESS);mach_port_deallocate(mach_task_self(),thread);
    CHECK(mach_eventlink_associate(pair[1],MACH_PORT_NULL,0,0,0,0,MELA_OPTION_ASSOCIATE_ON_WAIT)==KERN_SUCCESS);
    CHECK(mach_eventlink_associate(pair[1],MACH_PORT_NULL,0,0,0,0,MELA_OPTION_ASSOCIATE_ON_WAIT)==KERN_NAME_EXISTS);
    CHECK(mach_eventlink_signal(pair[1],0)==KERN_SUCCESS);CHECK(mach_eventlink_signal(pair[1],0)==KERN_SUCCESS);
    CHECK(mach_eventlink_wait_until(pair[0],&count,MELSW_OPTION_NO_WAIT,KERN_CLOCK_MACH_ABSOLUTE_TIME,0)==KERN_SUCCESS);CHECK(count==2);
    CHECK(mach_eventlink_wait_until(pair[0],&count,MELSW_OPTION_NO_WAIT,KERN_CLOCK_MACH_ABSOLUTE_TIME,0)==KERN_OPERATION_TIMED_OUT);CHECK(count==2);
    uint64_t begin=mach_absolute_time();CHECK(mach_eventlink_wait_until(pair[0],&count,MELSW_OPTION_NONE,KERN_CLOCK_MACH_ABSOLUTE_TIME,begin+ticks(15000000))==KERN_OPERATION_TIMED_OUT);CHECK(count==2);CHECK(mach_absolute_time()-begin>=ticks(10000000));puts("EVENTLINK_REAL_TIMEOUT");
    pthread_t worker;CHECK(!pthread_create(&worker,0,peer,0));CHECK(mach_eventlink_wait_until(pair[0],&count,MELSW_OPTION_NONE,KERN_CLOCK_MACH_ABSOLUTE_TIME,mach_absolute_time()+ticks(2000000000))==KERN_SUCCESS);CHECK(count==3);
    CHECK(mach_eventlink_signal_wait_until(pair[0],&count,0,MELSW_OPTION_NONE,KERN_CLOCK_MACH_ABSOLUTE_TIME,mach_absolute_time()+ticks(2000000000))==KERN_SUCCESS);CHECK(count==4);
    void* result=(void*)99;CHECK(!pthread_join(worker,&result));CHECK(!result);puts("EVENTLINK_REAL_THREAD_SIGNAL_WAIT_HANDOFF");
    CHECK(mach_eventlink_disassociate(pair[0],MELD_OPTION_NONE)==KERN_SUCCESS);CHECK(mach_eventlink_destroy(pair[0])==KERN_SUCCESS);CHECK(mach_eventlink_signal(pair[1],0)!=KERN_SUCCESS);mach_eventlink_destroy(pair[1]);
    puts("MACH_EVENTLINK_MIG_64BIT_COUNT_REAL_WAIT_SIGNAL_AND_LIFECYCLE_NATIVE_OK");return 0;
}
