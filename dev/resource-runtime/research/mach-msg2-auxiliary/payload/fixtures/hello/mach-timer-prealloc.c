#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <stdint.h>
#include <stdio.h>
#define CHECK(x) do{if(!(x)){printf("MACH_TIMER_FAILED line=%d %s\n",__LINE__,#x);return 1;}}while(0)
int main(void){
 setbuf(stdout,NULL);mach_port_t(*create)(void)=dlsym(RTLD_DEFAULT,"mk_timer_create");kern_return_t(*arm)(mach_port_t,uint64_t)=dlsym(RTLD_DEFAULT,"mk_timer_arm");kern_return_t(*cancel)(mach_port_t,uint64_t*)=dlsym(RTLD_DEFAULT,"mk_timer_cancel");CHECK(create&&arm&&cancel);mach_timebase_info_data_t timebase;CHECK(mach_timebase_info(&timebase)==0&&timebase.numer&&timebase.denom);uint64_t millisecond=1000000ull*timebase.denom/timebase.numer;
 mach_port_t port=create();CHECK(port);unsigned char bytes[256];
 for(unsigned i=0;i<16;i++){CHECK(arm(port,mach_absolute_time()+millisecond)==0);mach_msg_header_t* message=(void*)bytes;CHECK(mach_msg(message,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof bytes,port,1000,0)==0);CHECK(message->msgh_id==0&&message->msgh_local_port==port&&message->msgh_size>=sizeof *message);}
 uint64_t deadline=mach_absolute_time()+1000*millisecond,previous=0;CHECK(arm(port,deadline)==0);CHECK(cancel(port,&previous)==0&&previous>0);CHECK(mach_msg((void*)bytes,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof bytes,port,20,0)==MACH_RCV_TIMED_OUT);CHECK(mach_port_destroy(mach_task_self(),port)==0);
 for(unsigned i=0;i<32;i++){port=create();CHECK(port);CHECK(arm(port,mach_absolute_time()+1000*millisecond)==0);CHECK(mach_port_destroy(mach_task_self(),port)==0);}
 puts("MACH_TIMER_REAL_PREALLOC_REUSE_DELIVERY_CANCEL_AND_DESTROY_OK firings=16 armed_destructions=32");return 0;
}
