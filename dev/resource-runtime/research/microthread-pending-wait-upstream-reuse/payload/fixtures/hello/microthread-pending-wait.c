/* Exercise real duct-tape locks and wait/block functions with a controlled
 * scheduler. An internal mutex wake is not a wake of the armed XNU wait. */
#include <darlingserver/duct-tape.h>
#include <darlingserver/duct-tape/thread.h>
#include <darlingserver/duct-tape/hooks.internal.h>
#include <kern/timer_call.h>
#include <stdlib.h>
/* Kernel headers deliberately do not use the host libc stdio headers. */
extern int printf(const char *, ...);
extern int puts(const char *);

static dtape_thread_t owner, waiter;
static dtape_thread_t *active;
static dtape_mutex_t contended;
static unsigned mutex_suspends, wait_suspends, resumes;

static dtape_thread_t *current(void) { return active; }
static void resumed(void *context) {
    if (context != &waiter) abort();
    ++resumes;
}
static void suspended(void *context,
                      dtape_thread_continuation_callback_f continuation,
                      void *parameter, libsimple_lock_t *unlock) {
    if (context != &waiter || continuation || parameter != &waiter) {
        /* Internal mutex suspension has no continuation parameter. */
        if (context != &waiter || continuation || parameter || !unlock) abort();
    }
    dtape_thread_exiting(&waiter);
    if (unlock) {
        ++mutex_suspends;
        libsimple_lock_unlock(unlock);
        active = &owner;
        dtape_mutex_unlock(&contended);
        active = &waiter;
    } else {
        ++wait_suspends;
        thread_lock(&waiter.xnu_thread);
        thread_unblock(&waiter.xnu_thread, THREAD_AWAKENED);
        thread_unlock(&waiter.xnu_thread);
    }
    dtape_thread_entering(&waiter);
}

static const dtape_hooks_t hooks = {
    .current_thread = current,
    .thread_suspend = suspended,
    .thread_resume = resumed,
};
const dtape_hooks_t *dtape_hooks = &hooks;

int main(void) {
    owner.context = &owner;
    waiter.context = &waiter;
    active = &owner;
    thread_lock_init(&owner.xnu_thread);
    thread_lock_init(&waiter.xnu_thread);
    dtape_mutex_init(&contended);
    dtape_mutex_lock(&contended);
    active = &waiter;
    thread_lock(&waiter.xnu_thread);
    thread_mark_wait_locked(&waiter.xnu_thread, THREAD_UNINT);
    thread_unlock(&waiter.xnu_thread);

    /* A cooperative mutex suspension after assert_wait, before thread_block. */
    dtape_mutex_lock(&contended);
    dtape_mutex_unlock(&contended);
    wait_result_t result = thread_block_parameter(NULL, NULL);
    printf("PENDING_WAIT result=%d mutex_suspends=%u wait_suspends=%u resumes=%u state=%d\n",
           result, mutex_suspends, wait_suspends, resumes, waiter.xnu_thread.state);
    if (result != THREAD_AWAKENED || mutex_suspends != 1 || wait_suspends != 1 ||
        resumes != 2 || (waiter.xnu_thread.state & TH_WAIT)) return 1;

    /* A genuine wake before thread_block must skip suspension. */
    thread_lock(&waiter.xnu_thread);
    thread_mark_wait_locked(&waiter.xnu_thread, THREAD_UNINT);
    thread_unblock(&waiter.xnu_thread, THREAD_AWAKENED);
    thread_unlock(&waiter.xnu_thread);
    result = thread_block_parameter(NULL, NULL);
    if (result != THREAD_AWAKENED || wait_suspends != 1 || resumes != 3) return 2;
    puts("MICROTHREAD_PENDING_WAIT_AND_EARLY_WAKE_OK");
    return 0;
}
