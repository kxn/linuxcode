/* Actual XNU wait and duct-tape mutex bridge for the C++ ucontext regression.
 * Only fixture construction and host scheduler hooks live here. */
#include <darlingserver/duct-tape.h>
#include <darlingserver/duct-tape/thread.h>
#include <darlingserver/duct-tape/hooks.internal.h>
#include <stdlib.h>

extern void *fixture_current_context(void);
extern void fixture_suspend(void *, dtape_thread_continuation_callback_f, void *, libsimple_lock_t *);
extern void fixture_resume(void *);
extern void fixture_complete_continuation(void);

extern void abort(void);
static dtape_thread_t *fixture_threads[8];
static unsigned thread_count, consumed_waits;
static dtape_mutex_t mutex;

static dtape_thread_t *current(void) {
    void *context = fixture_current_context();
    for (unsigned i = 0; i < thread_count; ++i)
        if (fixture_threads[i]->context == context) return fixture_threads[i];
    return NULL;
}

static void fixture_log(dtape_log_level_t level, const char *message) {
    (void)level; (void)message;
}

static const dtape_hooks_t hooks = {
    .current_thread = current,
    .thread_suspend = fixture_suspend,
    .thread_resume = fixture_resume,
    .log = fixture_log,
};

void fixture_install_hooks(void) {
    dtape_hooks = &hooks;
    dtape_mutex_init(&mutex);
}

dtape_thread_t *fixture_create_thread(void *context) {
    if (thread_count == 8) abort();
    dtape_thread_t *thread = malloc(sizeof(*thread));
    if (!thread) abort();
    memset(thread, 0, sizeof(*thread));
    thread->context = context;
    thread_lock_init(&thread->xnu_thread);
    fixture_threads[thread_count++] = thread;
    return thread;
}

void fixture_owner_lock(void) { dtape_mutex_lock(&mutex); }
void fixture_owner_unlock(void) { dtape_mutex_unlock(&mutex); }

void fixture_wake_thread(void *context) {
    for (unsigned i = 0; i < thread_count; ++i) {
        if (fixture_threads[i]->context != context) continue;
        thread_lock(&fixture_threads[i]->xnu_thread);
        thread_unblock(&fixture_threads[i]->xnu_thread, THREAD_AWAKENED);
        thread_unlock(&fixture_threads[i]->xnu_thread);
        return;
    }
    abort();
}

static void finished_wait(void *parameter, wait_result_t result) {
    if (parameter != current() || result != THREAD_AWAKENED) abort();
    fixture_complete_continuation();
    abort();
}

int fixture_wait_for_wake(int continuation) {
    dtape_thread_t *thread = current();
    thread_lock(&thread->xnu_thread);
    thread_mark_wait_locked(&thread->xnu_thread, THREAD_UNINT);
    thread_unlock(&thread->xnu_thread);
    return thread_block_parameter(continuation ? finished_wait : NULL, thread);
}

int fixture_consumed_wait_then_mutex(void) {
    dtape_thread_t *thread = current();
    thread_lock(&thread->xnu_thread);
    thread_mark_wait_locked(&thread->xnu_thread, THREAD_UNINT);
    thread_unblock(&thread->xnu_thread, THREAD_AWAKENED);
    thread_unlock(&thread->xnu_thread);
    if (thread_block_parameter(NULL, NULL) != THREAD_AWAKENED) return 1;
    ++consumed_waits;
    // This is a different wait, in the SAME microthread execution segment.
    // Its mutex_link remains queued until the owner removes it on unlock.
    dtape_mutex_lock(&mutex);
    dtape_mutex_unlock(&mutex);
    return 0;
}

unsigned fixture_consumed_waits(void) { return consumed_waits; }
int fixture_mutex_queue_is_single(void) {
    dtape_mutex_link_t *first = TAILQ_FIRST(&mutex.dtape_queue_head);
    return first && TAILQ_NEXT(first, link) == NULL;
}
int fixture_mutex_queue_has_self_link(void) {
    dtape_mutex_link_t *first = TAILQ_FIRST(&mutex.dtape_queue_head);
    return first && TAILQ_NEXT(first, link) == first;
}
