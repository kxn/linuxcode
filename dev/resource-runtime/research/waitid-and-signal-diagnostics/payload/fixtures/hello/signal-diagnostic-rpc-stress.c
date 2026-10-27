#include <assert.h>
#include <mach/mach.h>
#include <mach/i386/thread_status.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <unistd.h>

extern void __simple_kprintf(const char *, ...);
static thread_t target;
static unsigned state_reads;
static volatile sig_atomic_t signals;
static void handler(int number) { if(number==SIGUSR1)signals++; }
static void *reader(void *unused)
{
    for(unsigned i=0;i<64;i++) {
        x86_thread_state64_t state; mach_msg_type_number_t count=x86_THREAD_STATE64_COUNT;
        assert(thread_get_state(target,x86_THREAD_STATE64,(thread_state_t)&state,&count)==KERN_SUCCESS);
        assert(count==x86_THREAD_STATE64_COUNT);
        __atomic_add_fetch(&state_reads,1,__ATOMIC_RELAXED);
        assert(kill(getpid(),SIGUSR1)==0);
    }
    return NULL;
}
int main(void)
{
    setbuf(stdout,NULL); struct sigaction action={0};action.sa_handler=handler;
    sigemptyset(&action.sa_mask);action.sa_flags=SA_RESTART;
    assert(sigaction(SIGUSR1,&action,NULL)==0); target=mach_thread_self();
    pthread_t workers[2];
    for(unsigned i=0;i<2;i++)assert(pthread_create(&workers[i],NULL,reader,NULL)==0);
    for(unsigned i=0;i<256;i++)__simple_kprintf("NATIVE_RPC_NORMAL_DIAGNOSTIC %u\n",i);
    for(unsigned i=0;i<2;i++)assert(pthread_join(workers[i],NULL)==0);
    assert(state_reads==128 && signals>0);
    printf("SIGNAL_DIAGNOSTIC_RPC_STRESS_OK state_reads=%u handled_signals=%d ordinary_log_RPCS=256\n",state_reads,(int)signals);
    assert(mach_port_deallocate(mach_task_self(),target)==KERN_SUCCESS);
    return 0;
}
