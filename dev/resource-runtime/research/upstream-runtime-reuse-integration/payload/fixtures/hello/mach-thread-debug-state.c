#include <mach/mach.h>
#include <mach/thread_act.h>
#include <mach/i386/thread_status.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static volatile uint64_t own_address;
static unsigned checks;
#define CHECK(expr) do { ++checks; if (!(expr)) { fprintf(stderr,"MACH_DEBUG_STATE_CHECK_FAILED line=%d\n",__LINE__); return 1; } } while (0)
int main(void) {
    thread_t thread=mach_thread_self();
    CHECK(MACH_PORT_VALID(thread));
    x86_debug_state_t original;
    mach_msg_type_number_t count=x86_DEBUG_STATE_COUNT;
    CHECK(thread_get_state(thread,x86_DEBUG_STATE,(thread_state_t)&original,&count)==KERN_SUCCESS);
    CHECK(count==x86_DEBUG_STATE_COUNT);
    CHECK(original.dsh.flavor==x86_DEBUG_STATE64 && original.dsh.count==x86_DEBUG_STATE64_COUNT);
    x86_debug_state64_t direct;
    count=x86_DEBUG_STATE64_COUNT;
    CHECK(thread_get_state(thread,x86_DEBUG_STATE64,(thread_state_t)&direct,&count)==KERN_SUCCESS);
    CHECK(count==x86_DEBUG_STATE64_COUNT);
    CHECK(memcmp(&direct,&original.uds.ds64,sizeof direct)==0);
    x86_debug_state_t bad;
    count=x86_DEBUG_STATE_COUNT-1;
    CHECK(thread_get_state(thread,x86_DEBUG_STATE,(thread_state_t)&bad,&count)==KERN_INVALID_ARGUMENT);
    CHECK(count==x86_DEBUG_STATE_COUNT-1);
    x86_debug_state32_t narrow;
    count=x86_DEBUG_STATE32_COUNT;
    CHECK(thread_get_state(thread,x86_DEBUG_STATE32,(thread_state_t)&narrow,&count)==KERN_INVALID_ARGUMENT);
    natural_t oversized[x86_DEBUG_STATE_COUNT+1];
    memcpy(oversized,&original,sizeof original);oversized[x86_DEBUG_STATE_COUNT]=0;
    CHECK(thread_set_state(thread,x86_DEBUG_STATE,oversized,x86_DEBUG_STATE_COUNT+1)==KERN_INVALID_ARGUMENT);
    bad=original;bad.dsh.count=x86_DEBUG_STATE64_COUNT-1;
    CHECK(thread_set_state(thread,x86_DEBUG_STATE,(thread_state_t)&bad,x86_DEBUG_STATE_COUNT)==KERN_INVALID_ARGUMENT);
    uint64_t before[8],changed[8],after[8];
    memcpy(before,&original.uds.ds64,sizeof before);memcpy(changed,before,sizeof changed);
    changed[0]=(uintptr_t)&own_address;changed[7]=0; /* Never enable a breakpoint. */
    x86_debug_state_t modified=original;memcpy(&modified.uds.ds64,changed,sizeof changed);
    CHECK(thread_set_state(thread,x86_DEBUG_STATE,(thread_state_t)&modified,x86_DEBUG_STATE_COUNT)==KERN_SUCCESS);
    count=x86_DEBUG_STATE64_COUNT;
    kern_return_t read_status=thread_get_state(thread,x86_DEBUG_STATE64,(thread_state_t)&direct,&count);
    /* Restore before evaluating any subsequent assertion, including failures. */
    kern_return_t restore_status=thread_set_state(thread,x86_DEBUG_STATE64,(thread_state_t)&original.uds.ds64,x86_DEBUG_STATE64_COUNT);
    CHECK(restore_status==KERN_SUCCESS);
    CHECK(read_status==KERN_SUCCESS);
    memcpy(after,&direct,sizeof after);CHECK(after[0]==changed[0] && after[7]==0);
    count=x86_DEBUG_STATE_COUNT;
    CHECK(thread_get_state(thread,x86_DEBUG_STATE,(thread_state_t)&modified,&count)==KERN_SUCCESS);
    CHECK(memcmp(&modified.uds.ds64,&original.uds.ds64,sizeof direct)==0);
    CHECK(mach_port_deallocate(mach_task_self(),thread)==KERN_SUCCESS);
    printf("LINUXCODE_MACH_DEBUG_STATE_ROUNDTRIP_OK checks=%u DR6=%llx\n",checks,(unsigned long long)before[6]);
    return 0;
}
