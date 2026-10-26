#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct work_interval {uint64_t thread_id,work_interval_id;uint32_t create_flags,port;};
typedef struct work_interval* work_interval_t;
typedef struct work_interval_instance* work_interval_instance_t;
#define WORK_INTERVAL_FLAG_IGNORED 0x20
static unsigned calls,last_op;static int backend_error;static uint64_t observed[12];
static int __work_interval_ctl(uint32_t op,uint64_t id,void* data,size_t size) {
    assert(size==96 && id==UINT64_C(0x123456789abcdef0));++calls;last_op=op;memcpy(observed,data,96);
    if(backend_error){errno=backend_error;return -1;}
    if(op==6){uint64_t value=UINT64_C(0x100000083);memcpy((char*)data+8,&value,8);for(unsigned i=0;i<40;++i)((unsigned char*)data)[56+i]=i+1;}
    return 0;
}
#include "work_interval_instance.inc"
int main(void) {
    struct work_interval parent={0,UINT64_C(0x123456789abcdef0),0,0};
    work_interval_instance_t i=work_interval_instance_alloc(&parent);assert(i);assert(!work_interval_instance_get_id(i));
    work_interval_instance_set_start(i,UINT64_C(1)<<35);work_interval_instance_set_finish(i,(UINT64_C(1)<<35)+1);work_interval_instance_set_deadline(i,(UINT64_C(1)<<35)+2);work_interval_instance_set_complexity(i,(UINT64_C(1)<<50)+7);
    assert(!work_interval_instance_get_start(i) && !work_interval_instance_get_complexity(i));
    assert(!work_interval_instance_update(i) && !work_interval_instance_finish(i) && !calls);
    assert(!work_interval_instance_start(i));assert(calls==1 && last_op==6);assert(observed[0]==parent.work_interval_id && !observed[1]);assert(observed[2]==(UINT64_C(1)<<35) && observed[5]==(UINT64_C(1)<<50)+7);
    assert(work_interval_instance_get_id(i)==UINT64_C(0x100000083));assert(work_interval_instance_get_start(i)==(UINT64_C(1)<<35));assert(work_interval_instance_get_finish(i)==(UINT64_C(1)<<35)+1);assert(work_interval_instance_get_deadline(i)==(UINT64_C(1)<<35)+2);assert(work_interval_instance_get_complexity(i)==(UINT64_C(1)<<50)+7);
    unsigned char output[56];memset(output,0xa5,sizeof output);assert(work_interval_instance_get_telemetry_data(i,output,sizeof output)==output);for(unsigned j=0;j<40;++j)assert(output[j]==j+1);for(unsigned j=40;j<56;++j)assert(output[j]==0xa5);
    assert(!work_interval_instance_update(i) && last_op==7);
    backend_error=EIO;assert(work_interval_instance_finish(i)==-1 && errno==EIO && last_op==8);assert(work_interval_instance_get_id(i)==UINT64_C(0x100000083));assert(!work_interval_instance_get_start(i) && !work_interval_instance_get_finish(i) && !work_interval_instance_get_deadline(i) && !work_interval_instance_get_complexity(i));
    work_interval_instance_clear(i);assert(!work_interval_instance_get_id(i));memset(output,0,sizeof output);work_interval_instance_get_telemetry_data(i,output,4);assert(output[0]==1 && output[3]==4 && !output[4]);
    backend_error=ENOSYS;assert(work_interval_instance_start(i)==-1 && errno==ENOSYS && !work_interval_instance_get_id(i));work_interval_instance_free(i);
    parent.create_flags=WORK_INTERVAL_FLAG_IGNORED;i=work_interval_instance_alloc(&parent);unsigned prior=calls;assert(!work_interval_instance_start(i) && !work_interval_instance_update(i) && !work_interval_instance_finish(i) && prior==calls);work_interval_instance_free(i);
    assert(work_interval_instance_start(0)==-1 && errno==EINVAL);assert(work_interval_instance_update(0)==-1 && errno==EINVAL);assert(work_interval_instance_finish(0)==-1 && errno==EINVAL);assert(!work_interval_instance_alloc(0) && errno==EINVAL);
    puts("WORK_INTERVAL_INSTANCE_PAYLOAD_64BIT_FIELDS_LIFECYCLE_AND_BACKEND_ERRORS_HOST_OK");return 0;
}
