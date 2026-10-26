#pragma once
#include <stdint.h>
uint64_t sys_eventlink_signal(uint32_t port, uint64_t signal_count);
uint64_t sys_eventlink_wait(uint32_t port, uint64_t wait_count, uint64_t deadline, uint32_t clock_id, uint32_t options);
uint64_t sys_eventlink_signal_wait(uint32_t port, uint64_t wait_count, uint64_t signal_count, uint64_t deadline, uint32_t clock_id, uint32_t options);
