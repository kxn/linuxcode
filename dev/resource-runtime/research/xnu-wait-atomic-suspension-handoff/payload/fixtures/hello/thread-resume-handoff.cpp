/* Host regression for the actual C++ Thread scheduler. The queue boundary and
 * unused XNU lifecycle are controlled; Thread, ucontext and StackPool are real.
 * The companion C bridge executes actual XNU waits and duct-tape mutex code.
 * No Server::start(), dtape_init(), Darling boot or Mach-O execution occurs. */
#include <darlingserver/thread.hpp>
#include <darlingserver/server.hpp>
#include <darlingserver/call.hpp>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <string>
#include <thread>

using DarlingServer::Thread;
static std::deque<std::shared_ptr<Thread>> ready;
static std::shared_ptr<Thread> target;
static std::atomic<bool> injecting = false;
static bool injectAtSuspend = false;
static unsigned collisions, schedules, entering, exiting;
static bool waitCase = false, injectWaitAtSuspend = false, waitHookSeen = false;
static unsigned waitHookCount = 0, injectWaitHook = 1;
static libsimple_lock_t* waitHandoffLock = nullptr;
static std::thread nativeWakeWorker;
static std::thread injectedScheduler;
static thread_local bool isNativeWakeWorker = false;
static thread_local bool isInjectedScheduler = false;
static std::atomic<bool> wakeAttempted = false, wakeFinished = false;
static std::atomic<bool> schedulerEntered = false, schedulerFinished = false;
static unsigned waitCompletions = 0;
static void beginNativeWaitWake();

extern "C" {
void fixture_install_hooks();
dtape_thread_t* fixture_create_thread(void*);
void fixture_owner_lock();
void fixture_owner_unlock();
int fixture_consumed_wait_then_mutex();
unsigned fixture_consumed_waits();
int fixture_mutex_queue_is_single();
int fixture_mutex_queue_has_self_link();
void fixture_wake_thread(void*);
int fixture_wait_for_wake(int);
void* fixture_current_context() { return Thread::currentThread().get(); }
void fixture_suspend(void* context, dtape_thread_continuation_callback_f continuation,
                     void* parameter, libsimple_lock_t* unlock) {
    auto* thread = static_cast<Thread*>(context);
    if (waitCase && ++waitHookCount == injectWaitHook) {
        waitHookSeen = true;
        waitHandoffLock = unlock;
        if (injectWaitAtSuspend) injectAtSuspend = true;
        else beginNativeWaitWake();
    }
    if (continuation) thread->suspend([=] { continuation(parameter); }, unlock);
    else thread->suspend(nullptr, unlock);
}
void fixture_resume(void* context) { static_cast<Thread*>(context)->resume(); }
void fixture_complete_continuation() {
    ++waitCompletions;
    // Leave the successful real C continuation parked for inspection. Returning
    // would terminate an XNU thread, requiring boot/teardown outside this test.
    target->suspend();
    std::abort();
}
}

static void require(bool condition, const char* message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL %s (queued=%zu schedules=%u collisions=%u)\n",
                     message, ready.size(), schedules, collisions);
        std::fflush(nullptr);
        std::_Exit(1);
    }
}

// A separate native worker wakes while the old microthread still owns its
// context. If resume queues prematurely, that worker immediately consumes the
// item and executes real doWork(), reproducing the lost handoff deterministically.
static void wakeFromOtherWorker() {
    injecting = true;
    std::thread worker([] {
        for (unsigned i = 0; i < 3; ++i) target->resume();
    });
    worker.join();
    injecting = false;
}

extern "C" void __real_libsimple_lock_lock(libsimple_lock_t*);
extern "C" void __wrap_libsimple_lock_lock(libsimple_lock_t* lock) {
    if (isNativeWakeWorker) wakeAttempted = true;
    __real_libsimple_lock_lock(lock);
}

static void beginNativeWaitWake() {
    injecting = true;
    nativeWakeWorker = std::thread([] {
        isNativeWakeWorker = true;
        fixture_wake_thread(target.get());
        wakeFinished = true;
    });
    // Wait until the native waker has actually reached the real thread_lock's
    // native queue-lock boundary. No timing guesses or sleeps are involved.
    while (!wakeAttempted) std::this_thread::yield();
    if (!waitHandoffLock) {
        // Exact old C source releases its thread lock before entering the hook,
        // so force the real wake to finish inside the exposed race window.
        nativeWakeWorker.join();
        injecting = false;
    } else {
        require(!wakeFinished, "XNU wake bypassed retained handoff lock");
    }
}

extern "C" void queueThread(DarlingServer::Server*, std::shared_ptr<Thread> thread)
    asm("__wrap__ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE");
extern "C" void queueThread(DarlingServer::Server*, std::shared_ptr<Thread> thread) {
    ++schedules;
    if (injecting) {
        // Use another native scheduler worker. The XNU waker still owns the
        // thread lock until its resume hook returns; resuming synchronously on
        // the waker itself would manufacture a recursive-lock deadlock.
        injectedScheduler = std::thread([thread] {
            isInjectedScheduler = true;
            const auto enteredBefore = entering;
            thread->doWork();
            if (entering == enteredBefore) ++collisions;
            schedulerFinished = true;
        });
        // Old-source collision must be consumed before the original context
        // yields. A valid worker can instead enter, then await the waker's lock.
        while (!schedulerEntered && !schedulerFinished) std::this_thread::yield();
        if (schedulerFinished) injectedScheduler.join();
    } else {
        ready.push_back(std::move(thread));
    }
}

extern "C" int __real_setcontext(const ucontext_t*);
extern "C" int __wrap_setcontext(const ucontext_t* context) {
    if (injectAtSuspend) {
        injectAtSuspend = false;
        // Armed immediately before suspend(). Its first setcontext is the
        // transition back to doWork, after _suspended=true, before _running=false.
        if (waitCase) beginNativeWaitWake();
        else wakeFromOtherWorker();
    }
    return __real_setcontext(context);
}

// Only construction/context bookkeeping is replaced; C wait/mutex algorithms
// and enter/exit state bookkeeping use the actual implementations.
extern "C" dtape_task_t* __wrap_dtape_task_create(dtape_task_t*, uint32_t,
                                                  void* context, dserver_rpc_architecture_t) {
    return reinterpret_cast<dtape_task_t*>(context);
}
extern "C" dtape_thread_t* __wrap_dtape_thread_create(dtape_task_t*, uint64_t, void* context) {
    return fixture_create_thread(context);
}
extern "C" void __wrap_dtape_task_set_process_generation(dtape_task_t*, dtape_eternal_id_t, uint32_t) {}
extern "C" void __wrap_dtape_thread_dying(dtape_thread_t*) {}
extern "C" void __real_dtape_thread_entering(dtape_thread_t*);
extern "C" void __real_dtape_thread_exiting(dtape_thread_t*);
extern "C" void __wrap_dtape_thread_entering(dtape_thread_t* thread) {
    ++entering;
    if (isInjectedScheduler) schedulerEntered = true;
    __real_dtape_thread_entering(thread);
}
extern "C" void __wrap_dtape_thread_exiting(dtape_thread_t* thread) {
    ++exiting; __real_dtape_thread_exiting(thread);
}

static void runOne(bool checkCounters = true) {
    require(ready.size() == 1, "expected exactly one runnable microthread");
    auto thread = ready.front();
    ready.pop_front();
    thread->doWork();
    require(!Thread::currentThread(), "microthread context leaked into scheduler");
    if (checkCounters) require(entering == exiting, "unbalanced microthread enter/exit");
}

static void runConsumedWaitCase() {
    // Real owner and waiter microthreads share a real duct-tape mutex.
    auto owner = std::make_shared<Thread>(Thread::KernelThreadConstructorTag{});
    owner->registerWithProcess();
    owner->startKernelThread([&] {
        fixture_owner_lock();
        owner->suspend();
        fixture_owner_unlock();
    });
    runOne();
    unsigned completed = 0;
    target->startKernelThread([&] {
        require(fixture_consumed_wait_then_mutex() == 0, "actual early wait did not complete");
        ++completed;
    });
    runOne();
    require(fixture_consumed_waits() == 1 && completed == 0,
            "wait guard did not consume early wake before independent mutex wait");
    require(fixture_mutex_queue_is_single(), "mutex waiter was not queued exactly once");
    if (!ready.empty()) {
        // Consume the erroneous leftover wake once. Real mutex_lock now inserts
        // the same intrusive mutex_link a second time while its owner holds it.
        runOne();
        std::fprintf(stderr, "OBSERVED same_segment_mutex_self_link=%d consumed_waits=%u\n",
                     fixture_mutex_queue_has_self_link(), fixture_consumed_waits());
        require(false, "consumed XNU wake resumed a later independent mutex wait");
    }
    owner->resume();
    runOne();
    runOne();
    require(completed == 1 && ready.empty(), "actual owner unlock did not release waiter");
    std::printf("PASS consumed-wake-then-mutex consumed_waits=%u schedules=%u\n",
                fixture_consumed_waits(), schedules);
}

class ActiveCall final : public DarlingServer::Call {
    unsigned& _completed;
public:
    ActiveCall(unsigned& completed, dserver_rpc_callhdr_t* header):
        Call(target, DarlingServer::Address{}, header), _completed(completed) {}
    Number number() const override { return Number::Invalid; }
    void processCall() override {
        require(target->activeCall().get() == this, "fixture call did not become active");
        target->notifyDead();
        require(fixture_wait_for_wake(0) == 0, "dead active call's XNU wait failed");
        ++_completed;
        // Keep the actual call active: its teardown needs initialized XNU state,
        // while this case isolates wake delivery to a dead thread's active call.
    }
};

static void runDeadActiveCallCase() {
    waitCase = true;
    injectWaitAtSuspend = true;
    require(DarlingServer::threadRegistry().registerEntry(target), "could not register fixture thread");
    unsigned completed = 0;
    dserver_rpc_callhdr_t header{};
    target->setPendingCall(std::make_shared<ActiveCall>(completed, &header));
    DarlingServer::Server::sharedInstance().scheduleThread(target);
    runOne(false);
    if (nativeWakeWorker.joinable()) nativeWakeWorker.join();
    if (injectedScheduler.joinable()) injectedScheduler.join();
    injecting = false;
    if (completed == 0 && ready.size() == 1) runOne();
    require(target->isDead() && target->activeCall(), "dead active call fixture was not retained");
    // The controlled scheduler immediately executes wake deliveries on the
    // waking native worker. A correct atomic handoff completes the actual wait.
    require(completed == 1 && ready.empty(), "dead thread's active call failed to resume");
    std::printf("PASS dead-active-call schedules=%u entered=%u exited=%u\n",
                schedules, entering, exiting);
}

static void runAtomicWaitCase(const std::string& scenario) {
    waitCase = true;
    injectWaitAtSuspend = scenario.find("handoff") != std::string::npos;
    const bool continuation = scenario.find("continuation") != std::string::npos;
    const bool rewait = scenario.find("rewait") != std::string::npos;
    if (rewait) injectWaitHook = 2;
    target->startKernelThread([&] {
        require(fixture_wait_for_wake(continuation) == 0, "actual XNU wait failed");
        require(!continuation, "real C continuation returned to discarded stack");
        ++waitCompletions;
    });
    runOne(false);
    if (rewait) {
        require(waitHookCount == 1 && !waitHookSeen && ready.empty(),
                "initial continuation wait did not suspend for spurious resume");
        // A scheduler-only resume leaves TH_WAIT intact. The actual C
        // thread_continuation_callback must recheck it and suspend again;
        // inject the real XNU wake in this second loop's handoff window.
        target->resume();
        runOne(false);
    }
    if (nativeWakeWorker.joinable()) nativeWakeWorker.join();
    if (injectedScheduler.joinable()) injectedScheduler.join();
    injecting = false;
    if (waitCompletions == 0 && ready.size() == 1) runOne();
    require(waitHookSeen && wakeFinished, "native waker never reached real XNU wait");
    require(waitCompletions == 1 && ready.empty(), "XNU wake was lost at scheduler handoff");
    require(collisions == 0 && entering == exiting, "wake ran before old context yielded");
    std::printf("PASS %s retained_lock=%d schedules=%u entered=%u exited=%u\n",
                scenario.c_str(), waitHandoffLock != nullptr, schedules, entering, exiting);
}

int main(int argc, char** argv) {
    require(argc == 3, "usage: probe CASE PRIVATE_PREFIX");
    const std::string scenario = argv[1];
    // Construct only a private socket/idle worker queue. Never start the server.
    new DarlingServer::Server(argv[2]);
    fixture_install_hooks();
    target = std::make_shared<Thread>(Thread::KernelThreadConstructorTag{});
    target->registerWithProcess();
    if (scenario == "consumed-wake-then-mutex" || scenario == "dead-active-call" ||
        scenario.find("wait-") == 0) {
        if (scenario == "consumed-wake-then-mutex") runConsumedWaitCase();
        else if (scenario == "dead-active-call") runDeadActiveCallCase();
        else runAtomicWaitCase(scenario);
        std::fflush(nullptr);
        std::_Exit(0);
    }
    unsigned completed = 0;
    const bool continuation = scenario.find("continuation") != std::string::npos;
    const bool handoff = scenario.find("handoff") != std::string::npos;
    const bool noSuspend = scenario == "return-with-wake";
    target->startKernelThread([&] {
        require(Thread::currentThread() == target, "wrong active microthread");
        if (noSuspend) wakeFromOtherWorker();
        if (noSuspend) { ++completed; return; }
        injectAtSuspend = handoff;
        if (continuation) {
            target->suspend([&] { ++completed; });
            require(false, "continuation suspension returned to discarded stack");
        } else {
            volatile unsigned stackCanary = 0x57414b45;
            target->suspend();
            require(stackCanary == 0x57414b45, "stackful resume corrupted stack");
            ++completed;
        }
    });
    runOne();
    if (noSuspend) {
        require(completed == 1 && ready.empty(), "wake rescheduled a finished microthread");
        // A previous wake must not resume a later, independent suspension.
        target->startKernelThread([&] { target->suspend(); ++completed; });
        runOne();
        require(completed == 1 && ready.empty(), "wake leaked into a later suspension");
        target->resume();
    } else {
        require(completed == 0, "suspension did not yield");
        if (!handoff) {
            require(ready.empty(), "unwoken suspension scheduled itself");
            target->resume();
        }
    }
    if (!noSuspend) require(ready.size() == 1, "wake was lost before scheduler handoff");
    runOne();
    require(completed == (noSuspend ? 2u : 1u), "wake did not complete suspended work");
    require(ready.empty() && collisions == 0, "premature or duplicate scheduling");
    require(schedules == (noSuspend ? 3u : 2u), "running wakes were not coalesced");
    std::printf("PASS %s schedules=%u entered=%u exited=%u collisions=%u\n",
                scenario.c_str(), schedules, entering, exiting, collisions);
    std::fflush(nullptr);
    // Keep opaque XNU fixtures alive: real teardown requires dtape_init, which
    // intentionally lies outside this isolated scheduling regression.
    std::_Exit(0);
}
