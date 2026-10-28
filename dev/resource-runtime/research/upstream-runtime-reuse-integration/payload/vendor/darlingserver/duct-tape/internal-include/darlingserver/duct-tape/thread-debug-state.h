#ifndef DARLINGSERVER_THREAD_DEBUG_STATE_H
#define DARLINGSERVER_THREAD_DEBUG_STATE_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <mach/kern_return.h>
#include <mach/message.h>
#include <mach/thread_status.h>
#include <mach/i386/thread_status.h>
#include <darlingserver/duct-tape/hooks.h>

/* The Mach ABI conversion is shared by get_state and set_state. Only the host
 * hook may access hardware state; no successful result is synthesized here. */
static inline kern_return_t dtape_x86_debug_state(void* context, bool is64,
        int flavor, thread_state_t state, mach_msg_type_number_t* count,
        bool write, dtape_hook_thread_debug_registers_f access) {
    if (!state || !count) return KERN_INVALID_ARGUMENT;
    bool wrapped = flavor == x86_DEBUG_STATE;
    mach_msg_type_number_t leaf_count = is64 ? x86_DEBUG_STATE64_COUNT : x86_DEBUG_STATE32_COUNT;
    mach_msg_type_number_t required = wrapped ? x86_DEBUG_STATE_COUNT : leaf_count;
    int expected = is64 ? x86_DEBUG_STATE64 : x86_DEBUG_STATE32;
    if ((!wrapped && flavor != expected) || *count < required || (write && *count != required))
        return KERN_INVALID_ARGUMENT;
    x86_debug_state_t* wrapper = (x86_debug_state_t*)state;
    void* payload = wrapped ? (is64 ? (void*)&wrapper->uds.ds64 : (void*)&wrapper->uds.ds32) : (void*)state;
    if (wrapped && write && (wrapper->dsh.flavor != expected || wrapper->dsh.count != leaf_count))
        return KERN_INVALID_ARGUMENT;
    if (!access) return KERN_NOT_SUPPORTED;
    uint64_t registers[8];
    if (write) {
        if (is64) memcpy(registers, payload, sizeof(registers));
        else {
            uint32_t narrow[8]; memcpy(narrow, payload, sizeof(narrow));
            for (unsigned index = 0; index != 8; ++index) registers[index] = narrow[index];
        }
    }
    dtape_debug_register_result_t result = access(context, registers, write);
    switch (result) {
        case dtape_debug_register_success: break;
        case dtape_debug_register_invalid: return KERN_INVALID_ARGUMENT;
        case dtape_debug_register_denied: return KERN_PROTECTION_FAILURE;
        case dtape_debug_register_no_thread: return KERN_TERMINATED;
        case dtape_debug_register_unsupported: return KERN_NOT_SUPPORTED;
        default: return KERN_FAILURE;
    }
    if (!write) {
        if (is64) memcpy(payload, registers, sizeof(registers));
        else {
            uint32_t narrow[8];
            for (unsigned index = 0; index != 8; ++index) narrow[index] = (uint32_t)registers[index];
            memcpy(payload, narrow, sizeof(narrow));
        }
        if (wrapped) { wrapper->dsh.flavor = expected; wrapper->dsh.count = leaf_count; }
        *count = required;
    }
    return KERN_SUCCESS;
}
#endif
