#include <darlingserver/duct-tape/thread-debug-state.h>
extern int linux_debug_state_host_access(void*, uint64_t[8], bool);
static dtape_debug_register_result_t access(void* context,uint64_t regs[8],bool write) {
    return (dtape_debug_register_result_t)linux_debug_state_host_access(context,regs,write);
}
int test_mach_debug_state(void* context,int is64,int flavor,void* state,unsigned* count,int write) {
    return dtape_x86_debug_state(context,is64,flavor,state,count,write,access);
}
int test_mach_debug_constant(int key) {
    switch(key) {
        case 0:return x86_DEBUG_STATE;
        case 1:return x86_DEBUG_STATE32;
        case 2:return x86_DEBUG_STATE64;
        case 3:return x86_DEBUG_STATE_COUNT;
        case 4:return x86_DEBUG_STATE32_COUNT;
        case 5:return x86_DEBUG_STATE64_COUNT;
        case 6:return KERN_INVALID_ARGUMENT;
        case 7:return KERN_PROTECTION_FAILURE;
        case 8:return KERN_TERMINATED;
        case 9:return KERN_NOT_SUPPORTED;
        case 10:return KERN_FAILURE;
        case 11:return dtape_debug_register_denied;
        case 12:return dtape_debug_register_no_thread;
        case 13:return dtape_debug_register_unsupported;
        case 14:return dtape_debug_register_failure;
        default:return -1;
    }
}
