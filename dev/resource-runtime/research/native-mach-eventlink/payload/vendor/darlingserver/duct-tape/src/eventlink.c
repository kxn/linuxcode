#include <darlingserver/duct-tape.h>
#include <ipc/ipc_eventlink.h>

uint64_t dtape_eventlink_signal(uint32_t port, uint64_t signal_count)
{
    return mach_eventlink_signal_trap(port, signal_count);
}

uint64_t dtape_eventlink_wait(uint32_t port, uint64_t wait_count, uint64_t deadline, uint32_t clock_id, uint32_t options)
{
    return mach_eventlink_wait_until_trap(port, wait_count, options, clock_id, deadline);
}

uint64_t dtape_eventlink_signal_wait(uint32_t port, uint64_t wait_count, uint64_t signal_count, uint64_t deadline, uint32_t clock_id, uint32_t options)
{
    return mach_eventlink_signal_wait_until_trap(port, wait_count, signal_count, options, clock_id, deadline);
}
