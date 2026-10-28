/* Host regression of real checkout/checkin and Process lifecycle. Real Linux
 * pipes carry success EOF or the failure byte. Only monitor dispatch order,
 * reply transport and XNU object construction/destruction are controlled. */
#include <darlingserver/thread.hpp>
#include <darlingserver/server.hpp>
#include <darlingserver/call.hpp>
#include <darlingserver/process.hpp>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <map>
#include <string>
#include <thread>
#include <vector>
#include <sys/syscall.h>
#include <unistd.h>

using namespace DarlingServer;
static std::shared_ptr<Process> process, parent;
static std::shared_ptr<Thread> mainThread;
static std::vector<std::function<void()>> deferredCleanup;
static std::deque<std::shared_ptr<Thread>> queued;
static std::vector<dserver_rpc_replyhdr_t> replies;
static unsigned tasksCreated, tasksReleased, tasksDying, threadDeaths;
static std::atomic<pid_t> childID{0};
static std::string scenario;
static void require(bool value, const char* why) {
    if (!value) {
        std::fprintf(stderr, "FAIL %s created=%u released=%u dying=%u thread_deaths=%u replies=%zu\n",
                     why, tasksCreated, tasksReleased, tasksDying, threadDeaths, replies.size());
        std::fflush(nullptr); std::_Exit(1);
    }
}

struct DTapeHooks {
    static void parentOf(Process& p, const std::shared_ptr<Process>& q) { p._parentProcess = q; }
    static dtape_semaphore_t* forkSemaphore(Process& p) { return p._dtapeForkWaitSemaphore; }
    static bool pending(Process& p) { return p._pendingReplacement; }
    static bool dead(Process& p) { return p._dead; }
    static dtape_task_t* task(Process& p) { return p._dtapeTask; }
    static uint32_t version(Process& p) { return p._pidVersion; }
    static void responsibility(Process& p, Process::Responsibility value) { p._responsibility = value; }
    static Process::Responsibility self(Process& p) { return {p._nspid, p._uniqueID, p._eid}; }
    static std::vector<std::shared_ptr<Monitor>> monitors() { return Server::sharedInstance()._monitors; }
};

/* C++ permits access checking to be bypassed by an explicit instantiation.
 * This fixture-only member pointer calls the actual stored monitor callback;
 * no altered production header or duplicate callback implementation is used. */
struct MonitorCallback {
    using type = std::function<void(std::shared_ptr<Monitor>, Monitor::Event)> Monitor::*;
    friend type member(MonitorCallback);
};
template<class Tag, typename Tag::type Pointer> struct PrivateMember {
    friend typename Tag::type member(Tag) { return Pointer; }
};
template struct PrivateMember<MonitorCallback, &Monitor::_callback>;

static std::map<dtape_semaphore_t*, int> semaphores;
extern "C" dtape_semaphore_t* __wrap_dtape_semaphore_create(dtape_task_t*, int count) {
    auto* key = reinterpret_cast<dtape_semaphore_t*>(new char);
    semaphores.emplace(key, count); return key;
}
extern "C" void __wrap_dtape_semaphore_destroy(dtape_semaphore_t* sem) {
    require(semaphores.erase(sem) == 1, "destroyed unknown semaphore");
    // Keep the address reserved to make stale-object reuse observable.
}
extern "C" void __wrap_dtape_semaphore_up(dtape_semaphore_t* sem) {
    auto it = semaphores.find(sem); require(it != semaphores.end(), "signaled null/stale semaphore");
    ++it->second;
}
extern "C" bool __wrap_dtape_semaphore_down_simple(dtape_semaphore_t* sem) {
    auto it = semaphores.find(sem);
    require(it != semaphores.end() && it->second > 0, "unexpected unready semaphore wait");
    --it->second; return true;
}
extern "C" dtape_task_t* __wrap_dtape_task_create(dtape_task_t*, uint32_t, void*, dserver_rpc_architecture_t) {
    ++tasksCreated; return reinterpret_cast<dtape_task_t*>(new char);
}
extern "C" void __wrap_dtape_task_release(dtape_task_t*) { ++tasksReleased; }
extern "C" void __wrap_dtape_task_dying(dtape_task_t*) { ++tasksDying; }
extern "C" void __wrap_dtape_task_set_process_generation(dtape_task_t*, dtape_eternal_id_t, uint32_t) {}
extern "C" void __wrap_dtape_task_set_audit_identity(dtape_task_t*, uint32_t, uint32_t) {}
extern "C" void __wrap_dtape_thread_dying(dtape_thread_t*) { ++threadDeaths; }
extern "C" void __wrap_dtape_thread_release(dtape_thread_t*) {}
extern "C" {
void fixture_install_hooks();
dtape_thread_t* fixture_create_thread(void*);
dtape_thread_t* __wrap_dtape_thread_create(dtape_task_t*, uint64_t, void* context) {
    return fixture_create_thread(context);
}
void* fixture_current_context() { return Thread::currentThread().get(); }
void fixture_suspend(void* context, dtape_thread_continuation_callback_f continuation,
                     void* argument, libsimple_lock_t* unlock) {
    auto* thread = static_cast<Thread*>(context);
    if (continuation) thread->suspend([=] { continuation(argument); }, unlock);
    else thread->suspend(nullptr, unlock);
}
void fixture_resume(void* context) { static_cast<Thread*>(context)->resume(); }
void fixture_complete_continuation() { std::abort(); }
}
extern "C" void cleanup(std::function<void()> function)
    asm("__wrap__ZN13DarlingServer6Thread11kernelAsyncESt8functionIFvvEE");
extern "C" void cleanup(std::function<void()> function) { deferredCleanup.push_back(std::move(function)); }
extern "C" void schedule(Server*, std::shared_ptr<Thread> thread)
    asm("__wrap__ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE");
extern "C" void schedule(Server*, std::shared_ptr<Thread> thread) { queued.push_back(std::move(thread)); }
extern "C" void transport(Server*, Message&& message)
    asm("__wrap__ZN13DarlingServer6Server11sendMessageEONS_7MessageE");
extern "C" void transport(Server*, Message&& message) {
    require(message.data().size() >= sizeof(dserver_rpc_replyhdr_t), "reply truncated");
    replies.push_back(*reinterpret_cast<dserver_rpc_replyhdr_t*>(message.data().data()));
}

static bool same(Process::Responsibility a, Process::Responsibility b) {
    return a.pid == b.pid && a.uniqueID == b.uniqueID && a.generation == b.generation;
}
static void run(Message&& message) {
    message.setPID(getpid());
    auto call = Call::callFromMessage(std::move(message));
    require(bool(call), "call was rejected before dispatch");
    auto thread = call->thread();
    require(bool(thread), "call has no managed thread");
    thread->doWork();
    require(!Thread::currentThread(), "microthread escaped dispatch");
}
static bool checkin(pid_t tid, bool isFork = false) {
    Message message(sizeof(dserver_rpc_call_checkin_t), 0);
    auto* call = reinterpret_cast<dserver_rpc_call_checkin_t*>(message.data().data());
    *call = {};
    call->header = {dserver_callnum_checkin, getpid(), tid, dserver_rpc_architecture_x86_64};
    call->body.is_fork = isFork; call->body.lifetime_listener_pipe = -1;
    const auto count = replies.size(); run(std::move(message));
    return replies.size() == count + 1 && replies.back().code == 0;
}

struct ExecAttempt { int writer; std::shared_ptr<Monitor> monitor; };
static ExecAttempt checkout(bool macho = true, bool disclaim = false) {
    int fds[2]; require(pipe(fds) == 0, "pipe creation failed");
    auto before = DTapeHooks::monitors();
    Message message(disclaim ? sizeof(dserver_rpc_call_checkout_disclaim_t)
                             : sizeof(dserver_rpc_call_checkout_t), 0);
    auto* call = reinterpret_cast<dserver_rpc_call_checkout_t*>(message.data().data());
    *call = {};
    call->header = {disclaim ? dserver_callnum_checkout_disclaim : dserver_callnum_checkout,
                    getpid(), getpid(), dserver_rpc_architecture_x86_64};
    call->body.exec_listener_pipe = 0; call->body.executing_macho = macho;
    message.pushDescriptor(fds[0]);
    auto count = replies.size(); run(std::move(message));
    require(replies.size() == count + 1 && replies.back().code == 0, "checkout did not acknowledge listener");
    auto after = DTapeHooks::monitors();
    std::shared_ptr<Monitor> monitor;
    for (auto& candidate: after)
        if (candidate->fd()->fd() == fds[0]) monitor = candidate;
    require(bool(monitor), "checkout did not register real listener monitor");
    return {fds[1], monitor};
}
static void finish(ExecAttempt& exec, bool success) {
    if (!success) { char failure = 1; require(write(exec.writer, &failure, 1) == 1, "failure byte failed"); }
    require(close(exec.writer) == 0, "pipe writer close failed"); exec.writer = -1;
}
static void monitor(ExecAttempt& exec) {
    (exec.monitor.get()->*member(MonitorCallback{}))(exec.monitor, Monitor::Event::HangUp);
}
static void verifyChild() {
    const bool acknowledged = checkin(childID);
    const auto found = threadRegistry().lookupEntryByNSID(childID);
    std::fprintf(stdout, "OBSERVED child_acknowledged=%d child_registered=%d child_dead=%d\n",
                 acknowledged, bool(found), found ? (*found)->isDead() : 1);
    require(acknowledged && found && !(*found)->isDead(), "pthread checkin lost reply or registered thread");
}

int main(int argc, char** argv) {
    require(argc == 3, "usage: fixture CASE PRIVATE_PREFIX"); scenario = argv[1];
    new Server(argv[2]); fixture_install_hooks();
    std::thread child([] {
        childID = syscall(SYS_gettid);
        for (;;) std::this_thread::yield();
    });
    while (!childID) std::this_thread::yield();
    process = std::make_shared<Process>(getpid(), getpid(), Process::Architecture::x86_64);
    require(processRegistry().registerEntry(process), "process registration failed");
    parent = std::make_shared<Process>(getppid(), getppid(), Process::Architecture::x86_64);
    if (scenario == "initial-startup") DTapeHooks::parentOf(*process, parent);
    require(checkin(getpid()), "initial main checkin failed");
    mainThread = *threadRegistry().lookupEntryByNSID(getpid());
    const auto initialTask = DTapeHooks::task(*process);
    const auto initialVersion = DTapeHooks::version(*process);
    const auto initialCreates = tasksCreated;
    DTapeHooks::responsibility(*process, {getppid(), 0x1234, 0x5678});
    const auto initialResponsibility = process->responsibility();

    if (scenario == "pthread-not-fork" || scenario == "fork-once" || scenario == "initial-startup") {
        DTapeHooks::parentOf(*process, parent);
        if (scenario == "fork-once")
            require(checkin(getpid(), true), "main fork checkin failed");
        verifyChild();
        if (scenario == "fork-once")
            require(checkin(getpid(), false), "repeated main checkin failed");
        require(semaphores.at(DTapeHooks::forkSemaphore(*parent)) == (scenario == "fork-once" ? 1 : 0),
                "pthread/initial startup emitted spurious parent fork notification");
        require(tasksCreated == initialCreates, "startup checkin unexpectedly replaced task");
    } else if (scenario == "native-exec") {
        auto exec = checkout(false, true); finish(exec, true); monitor(exec);
        require(DTapeHooks::dead(*process) && mainThread->isDead() && tasksDying == 1,
                "native exec did not preserve process-death behavior");
        require(tasksCreated == initialCreates && same(process->responsibility(), initialResponsibility),
                "native exec replaced Darling task or claimed new responsibility");
    } else if (scenario == "failed-exec" || scenario == "failed-exec-late-monitor") {
        auto exec = checkout(true, true); finish(exec, false);
        if (scenario == "failed-exec") monitor(exec);
        else {
            auto second = checkout(true, false); finish(second, true);
            monitor(exec); monitor(second);
            require(checkin(getpid()), "success after failed listener did not check in");
        }
        require(same(process->responsibility(), initialResponsibility), "failed disclaim changed responsibility");
        const auto expected = scenario == "failed-exec" ? 0u : 1u;
        require(tasksCreated == initialCreates + expected, "failed exec changed task count");
        if (!expected) require(DTapeHooks::task(*process) == initialTask &&
                               DTapeHooks::version(*process) == initialVersion,
                               "failed exec changed task/version");
        verifyChild();
    } else {
        const bool disclaim = scenario == "disclaim-success";
        auto exec = checkout(true, disclaim); finish(exec, true);
        if (scenario == "exec-monitor-before-main") monitor(exec);
        require(checkin(getpid()), "exec main checkin failed");
        if (scenario == "exec-double-late-monitors") {
            auto second = checkout(); finish(second, true);
            monitor(exec);
            require(checkin(getpid()), "second exec main checkin failed");
            monitor(second);
        } else if (scenario != "exec-monitor-before-main") monitor(exec);
        verifyChild();
        const auto replacements = scenario == "exec-double-late-monitors" ? 2u : 1u;
        require(tasksCreated == initialCreates + replacements && tasksReleased == replacements &&
                DTapeHooks::task(*process) != initialTask && !DTapeHooks::pending(*process),
                "exec did not replace task exactly once per successful exec");
        require(same(process->responsibility(), disclaim ? DTapeHooks::self(*process) : initialResponsibility),
                "successful exec responsibility/disclaim mismatch");
    }
    std::printf("PASS %s created=%u released=%u dying=%u replies=%zu\n", scenario.c_str(),
                tasksCreated, tasksReleased, tasksDying, replies.size());
    std::fflush(nullptr); std::_Exit(0);
}
