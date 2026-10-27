#include <darling/emulation/xnu_syscall/bsd/impl/psynch/ulock_wait.h>

#include <sys/errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <libsimple/lock.h>

#include <darling/emulation/common/base.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/duct_errno.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>

struct timespec
{
	long tv_sec;
	long tv_nsec;
};

/* XNU's ulock_wait_cleanup returns the remaining registered waiters, not a
 * constant "possibly contended" result. libdispatch main-thread events rely
 * on the single-waiter result being exactly zero.
 * This private futex transport does not implement Darwin priority inheritance.
 */
#define ULOCK_WAIT_ADDRESSES 1024
struct ulock_waiters { void* address; unsigned opcode; unsigned count; };
static struct ulock_waiters waiters[ULOCK_WAIT_ADDRESSES];
static libsimple_lock_t waiters_lock=LIBSIMPLE_LOCK_INITIALIZER;
static uint32_t waiters_process;

static void ulock_waiters_process_init(void) {
    uint32_t pid=LINUX_SYSCALL(__NR_getpid);
    uint32_t busy=pid|0x80000000u;
    for (;;) {
        uint32_t seen=__atomic_load_n(&waiters_process,__ATOMIC_ACQUIRE);
        if(seen==pid)return;
        if(seen==busy) {__asm__ volatile("pause");continue;}
        if(!__atomic_compare_exchange_n(&waiters_process,&seen,busy,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))continue;
        /* A fork child must discard parent waiters and an inherited lock.
         * This runs once before any child thread can use the new registry. */
        libsimple_lock_init(&waiters_lock);
        for(unsigned i=0;i<ULOCK_WAIT_ADDRESSES;i++)waiters[i]=(struct ulock_waiters){0};
        __atomic_store_n(&waiters_process,pid,__ATOMIC_RELEASE);
        return;
    }
}

static long ulock_wait_error(int error,bool no_errno) {
    long result=-error;
    return no_errno ? result&~0x800L : result;
}

// timeout is in us
long sys_ulock_wait(uint32_t operation, void* addr, uint64_t value, uint32_t timeout)
{
    bool no_errno=operation&XNU_ULF_NO_ERRNO;
    unsigned opcode=operation&XNU_UL_OPCODE_MASK;
    if(opcode!=XNU_UL_COMPARE_AND_WAIT && opcode!=XNU_UL_UNFAIR_LOCK)
        return ulock_wait_error(EINVAL,no_errno);
    if(!addr || ((uintptr_t)addr&3))return ulock_wait_error(EINVAL,no_errno);
    ulock_waiters_process_init();
    struct ulock_waiters *entry=NULL,*unused=NULL;
    libsimple_lock_lock(&waiters_lock);
    for(unsigned i=0;i<ULOCK_WAIT_ADDRESSES;i++) {
        if(!waiters[i].count) {if(!unused)unused=&waiters[i];}
        else if(waiters[i].address==addr) {entry=&waiters[i];break;}
    }
    if(entry && entry->opcode!=opcode) {
        libsimple_lock_unlock(&waiters_lock);return ulock_wait_error(EDOM,no_errno);
    }
    if(!entry) {
        if(!unused) {libsimple_lock_unlock(&waiters_lock);return ulock_wait_error(ENOMEM,no_errno);}
        entry=unused;*entry=(struct ulock_waiters){addr,opcode,0};
    }
    ++entry->count;
    libsimple_lock_unlock(&waiters_lock);
    struct timespec ts={timeout/1000000,(timeout%1000000)*1000};
    long result=LINUX_SYSCALL(__NR_futex,addr,FUTEX_WAIT|FUTEX_PRIVATE_FLAG,
            value,timeout ? &ts : NULL);
    libsimple_lock_lock(&waiters_lock);
    unsigned remaining=--entry->count;
    if(!remaining)*entry=(struct ulock_waiters){0};
    libsimple_lock_unlock(&waiters_lock);
    if(result==0 || result==-LINUX_EAGAIN)return remaining;
    result=errno_linux_to_bsd(result);
    return result<0 && no_errno ? result&~0x800L : result;
}
