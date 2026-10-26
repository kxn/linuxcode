/* Darwin opaque work-interval instance ABI. CPU scheduling remains the
 * responsibility of __work_interval_ctl; errors are propagated unchanged.
 * The 96-byte payload and field/method semantics are verified against the
 * selected Intel reference, not an invented instance lifecycle. */
#include <string.h>
#include <stddef.h>

struct work_interval_instance {
    uint64_t work_interval_id;
    uint64_t instance_id;
    uint64_t start;
    uint64_t finish;
    uint64_t deadline;
    uint64_t complexity;
    uint32_t create_flags;
    uint32_t reserved;
    unsigned char telemetry[40];
};
_Static_assert(sizeof(struct work_interval_instance)==96,"work interval instance ABI");
_Static_assert(offsetof(struct work_interval_instance,complexity)==40,"complexity ABI");
_Static_assert(offsetof(struct work_interval_instance,telemetry)==56,"telemetry ABI");

work_interval_instance_t work_interval_instance_alloc(work_interval_t wi) {
    if(!wi){errno=EINVAL;return NULL;}
    work_interval_instance_t instance=malloc(sizeof(*instance));
    if(instance){memset(instance,0,sizeof(*instance));instance->work_interval_id=wi->work_interval_id;instance->create_flags=wi->create_flags;}
    return instance;
}
void work_interval_instance_free(work_interval_instance_t instance) {free(instance);}
void work_interval_instance_clear(work_interval_instance_t instance) {
    memset(&instance->instance_id,0,5*sizeof(uint64_t));
}
void work_interval_instance_set_start(work_interval_instance_t instance,uint64_t value) {instance->start=value;}
void work_interval_instance_set_finish(work_interval_instance_t instance,uint64_t value) {instance->finish=value;}
void work_interval_instance_set_deadline(work_interval_instance_t instance,uint64_t value) {instance->deadline=value;}
void work_interval_instance_set_complexity(work_interval_instance_t instance,uint64_t value) {instance->complexity=value;}
uint64_t work_interval_instance_get_id(work_interval_instance_t instance) {return instance->instance_id;}
uint64_t work_interval_instance_get_start(work_interval_instance_t instance) {return instance->instance_id?instance->start:0;}
uint64_t work_interval_instance_get_finish(work_interval_instance_t instance) {return instance->instance_id?instance->finish:0;}
uint64_t work_interval_instance_get_deadline(work_interval_instance_t instance) {return instance->instance_id?instance->deadline:0;}
uint64_t work_interval_instance_get_complexity(work_interval_instance_t instance) {return instance->instance_id?instance->complexity:0;}
void* work_interval_instance_get_telemetry_data(work_interval_instance_t instance,void* output,size_t size) {
    return memmove(output,instance->telemetry,size<sizeof(instance->telemetry)?size:sizeof(instance->telemetry));
}
int work_interval_instance_start(work_interval_instance_t instance) {
    if(!instance){errno=EINVAL;return -1;}
    if(instance->create_flags&WORK_INTERVAL_FLAG_IGNORED)return 0;
    return __work_interval_ctl(6,instance->work_interval_id,instance,sizeof(*instance));
}
int work_interval_instance_update(work_interval_instance_t instance) {
    if(!instance){errno=EINVAL;return -1;}
    if(!instance->instance_id || (instance->create_flags&WORK_INTERVAL_FLAG_IGNORED))return 0;
    return __work_interval_ctl(7,instance->work_interval_id,instance,sizeof(*instance));
}
int work_interval_instance_finish(work_interval_instance_t instance) {
    if(!instance){errno=EINVAL;return -1;}
    if(!instance->instance_id || (instance->create_flags&WORK_INTERVAL_FLAG_IGNORED))return 0;
    int result=__work_interval_ctl(8,instance->work_interval_id,instance,sizeof(*instance));
    memset(&instance->start,0,4*sizeof(uint64_t));
    return result;
}
