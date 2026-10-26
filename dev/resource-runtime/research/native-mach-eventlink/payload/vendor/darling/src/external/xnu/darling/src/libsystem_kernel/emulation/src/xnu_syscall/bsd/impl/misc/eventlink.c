#include <darling/emulation/xnu_syscall/bsd/impl/misc/eventlink.h>
#include <darlingserver/rpc.h>
#include <mach/mach_eventlink_types.h>
#include <mach/kern_return.h>

uint64_t sys_eventlink_signal(uint32_t port, uint64_t signal_count)
{
    uint64_t value=0;
    if(dserver_rpc_eventlink_signal(port,signal_count,&value)<0)
        return encode_eventlink_count_and_error(0,KERN_FAILURE);
    return value;
}
uint64_t sys_eventlink_wait(uint32_t port, uint64_t wait_count, uint64_t deadline, uint32_t clock_id, uint32_t options)
{
    uint64_t value=0;
    if(dserver_rpc_eventlink_wait(port,wait_count,deadline,clock_id,options,&value)<0)
        return encode_eventlink_count_and_error(0,KERN_FAILURE);
    return value;
}
uint64_t sys_eventlink_signal_wait(uint32_t port, uint64_t wait_count, uint64_t signal_count, uint64_t deadline, uint32_t clock_id, uint32_t options)
{
    uint64_t value=0;
    if(dserver_rpc_eventlink_signal_wait(port,wait_count,signal_count,deadline,clock_id,options,&value)<0)
        return encode_eventlink_count_and_error(0,KERN_FAILURE);
    return value;
}
