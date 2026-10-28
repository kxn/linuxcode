/* Actual IRQ-safe XNU wait queue and dtape signal-entry regression bridge. */
#include <darlingserver/duct-tape.h>
#include <darlingserver/duct-tape/thread.h>
#include <darlingserver/duct-tape/hooks.internal.h>
#include <kern/waitq.h>
#include <stdlib.h>
extern void abort(void);

extern void *fixture_current_context(void);
extern void fixture_suspend(void *, dtape_thread_continuation_callback_f, void *, libsimple_lock_t *);
extern void fixture_resume(void *);
static dtape_thread_t *fixture_thread;
static unsigned resume_hooks;
static int observed_state, observed_result, observed_linked;
static struct waitq queue;
static const event64_t event = 0x534947455843;

static dtape_thread_t *current(void) {
    return fixture_thread && fixture_thread->context == fixture_current_context() ? fixture_thread : NULL;
}
static void resume(void *context) { ++resume_hooks; fixture_resume(context); }
static void log_message(dtape_log_level_t level, const char *message) { (void)level; (void)message; }
static const dtape_hooks_t hooks = {
    .current_thread = current, .thread_suspend = fixture_suspend,
    .thread_resume = resume, .log = log_message,
};
void fixture_install_hooks(void) { dtape_hooks = &hooks; }
dtape_thread_t *fixture_create_thread(void *context) {
    if (fixture_thread) abort();
    fixture_thread = malloc(sizeof(*fixture_thread));
    if (!fixture_thread) abort();
    memset(fixture_thread, 0, sizeof(*fixture_thread));
    fixture_thread->context = context;
    thread_lock_init(&fixture_thread->xnu_thread);
    return fixture_thread;
}
static void observe(void) {
    observed_state = fixture_thread->xnu_thread.state;
    observed_result = fixture_thread->xnu_thread.wait_result;
    observed_linked = fixture_thread->xnu_thread.waitq != NULL;
}
int fixture_sigexc_case(int scenario) {
    thread_t thread = &fixture_thread->xnu_thread;
    if (waitq_init(&queue, SYNC_POLICY_FIFO | SYNC_POLICY_DISABLE_IRQ) != KERN_SUCCESS) return 10;
    if (scenario == 2) {
        thread->state = TH_RUN;
        thread->wait_result = THREAD_AWAKENED;
        dtape_thread_sigexc_enter(fixture_thread);
        observe();
        return observed_state == TH_RUN && observed_result == THREAD_AWAKENED &&
               resume_hooks == 0 ? 0 : 11;
    }
    if (waitq_assert_wait64(&queue, event, THREAD_ABORTSAFE, 0) != THREAD_WAITING) return 12;
    if (scenario == 3) {
        // The existing thread_mark_wait_locked ignores the interruptibility
        // argument. Construct the actual TH_UNINT state explicitly here to
        // test signal-entry policy without claiming to fix that separate API.
        thread_lock(thread); thread->state |= TH_UNINT; thread_unlock(thread);
    }
    if (scenario == 0) {
        if (waitq_wakeup64_one(&queue, event, THREAD_AWAKENED, WAITQ_ALL_PRIORITIES) != KERN_SUCCESS) return 13;
    }
    dtape_thread_sigexc_enter(fixture_thread);
    observe();
    if (scenario == 0) {
        if (observed_result != THREAD_AWAKENED || observed_linked || !(observed_state & TH_RUN)) return 14;
        return thread_block_parameter(NULL, NULL) == THREAD_AWAKENED ? 0 : 15;
    }
    if (scenario == 1) {
        if (observed_result != THREAD_INTERRUPTED || observed_linked || !(observed_state & TH_RUN) ||
            resume_hooks != 1) return 16;
        if (waitq_wakeup64_one(&queue, event, THREAD_AWAKENED, WAITQ_ALL_PRIORITIES) != KERN_NOT_WAITING) return 17;
        return thread_block_parameter(NULL, NULL) == THREAD_INTERRUPTED ? 0 : 18;
    }
    if (scenario == 3) {
        if (observed_result != THREAD_WAITING || !observed_linked ||
            (observed_state & (TH_WAIT | TH_UNINT)) != (TH_WAIT | TH_UNINT) || resume_hooks != 0) return 19;
        if (waitq_wakeup64_one(&queue, event, THREAD_AWAKENED, WAITQ_ALL_PRIORITIES) != KERN_SUCCESS) return 20;
        return thread_block_parameter(NULL, NULL) == THREAD_AWAKENED ? 0 : 21;
    }
    return 22;
}
int fixture_observed_state(void) { return observed_state; }
int fixture_observed_result(void) { return observed_result; }
int fixture_observed_linked(void) { return observed_linked; }
unsigned fixture_resume_hooks(void) { return resume_hooks; }
