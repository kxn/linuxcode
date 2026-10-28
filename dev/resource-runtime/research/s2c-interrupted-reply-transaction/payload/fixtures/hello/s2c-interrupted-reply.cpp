/* Host-only transaction regression. Thread::_s2cPerform, _mmap/_munmap,
 * Call::callFromMessage, Message, Registry, ucontext and StackPool are real.
 * The semaphore/transport boundary deterministically injects one interrupted
 * wait, then a real-format reply. No Darling server event loop is started. */
#include <darlingserver/thread.hpp>
#include <darlingserver/server.hpp>
#include <darlingserver/call.hpp>
#include <darlingserver/process.hpp>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <map>
#include <string>
#include <sys/mman.h>
#include <unistd.h>

using namespace DarlingServer;
static std::shared_ptr<Thread> target, caller;
static std::deque<std::shared_ptr<Thread>> runnable;
static std::deque<dserver_s2c_msgnum_t> requests;
static std::string scenario;
static unsigned sent, received, interruptions, replyWaits;
static bool acquireInterrupted;
static const uintptr_t expectedAddress = 0x12345000;
static void require(bool value, const char* why) {
    if (!value) {
        std::fprintf(stderr, "FAIL %s sent=%u received=%u interruptions=%u reply_waits=%u\n",
                     why, sent, received, interruptions, replyWaits);
        std::fflush(nullptr); std::_Exit(1);
    }
}

/* Existing production friend is used only for construction/inspection; the
 * transaction and reply ingestion execute unchanged production functions. */
struct DTapeHooks {
    static dtape_semaphore_t* perform(Thread& t) { return t._s2cPerformSempahore; }
    static dtape_semaphore_t* reply(Thread& t) { return t._s2cReplySempahore; }
    static bool pending(Thread& t) { return bool(t._s2cReply); }
    static void active(Thread& t, std::shared_ptr<Call> c) { t._activeCall = c; }
    static uintptr_t mmap(Thread& t, int& error) {
        return t._mmap(0, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS,
                       -1, 0, error);
    }
    static int munmap(Thread& t, int& error) { return t._munmap(expectedAddress, 4096, error); }
};

struct Semaphore { int count; };
static std::map<dtape_semaphore_t*, Semaphore> semaphores;
extern "C" dtape_semaphore_t* __wrap_dtape_semaphore_create(dtape_task_t*, int count) {
    auto key = reinterpret_cast<dtape_semaphore_t*>(new char);
    semaphores.emplace(key, Semaphore{count}); return key;
}
extern "C" void __wrap_dtape_semaphore_destroy(dtape_semaphore_t* sem) {
    require(semaphores.erase(sem) == 1, "destroyed unknown semaphore");
    delete reinterpret_cast<char*>(sem);
}
extern "C" void __wrap_dtape_semaphore_up(dtape_semaphore_t* sem) {
    auto it = semaphores.find(sem);
    require(it != semaphores.end(), "signaled unknown semaphore"); ++it->second.count;
}

static void deliver() {
    require(!requests.empty(), "reply requested without outstanding request");
    const auto number = requests.front(); requests.pop_front();
    const auto size = number == dserver_s2c_msgnum_mmap ? sizeof(dserver_s2c_reply_mmap_t)
                                                     : sizeof(dserver_s2c_reply_munmap_t);
    Message reply(size, 0);
    auto* header = reinterpret_cast<dserver_s2c_replyhdr_t*>(reply.data().data());
    header->call_number = dserver_callnum_s2c;
    header->pid = getpid(); header->tid = getpid();
    header->architecture = dserver_rpc_architecture_x86_64;
    header->s2c_number = number;
    if (number == dserver_s2c_msgnum_mmap) {
        auto* body = reinterpret_cast<dserver_s2c_reply_mmap_t*>(header);
        body->address = expectedAddress; body->errno_result = 0;
    } else {
        auto* body = reinterpret_cast<dserver_s2c_reply_munmap_t*>(header);
        body->return_value = 0; body->errno_result = 0;
    }
    reply.setPID(getpid());
    ++received;
    require(!Call::callFromMessage(std::move(reply)), "reply unexpectedly produced a call");
}

extern "C" bool __wrap_dtape_semaphore_down_simple(dtape_semaphore_t* sem) {
    auto it = semaphores.find(sem);
    require(it != semaphores.end(), "waited on unknown semaphore");
    if (sem == DTapeHooks::perform(*target) && scenario == "acquire-interrupted" &&
        !acquireInterrupted) {
        acquireInterrupted = true; ++interruptions; return false;
    }
    if (sem == DTapeHooks::reply(*target)) {
        ++replyWaits;
        if (sent == 1 && scenario != "normal" && scenario != "acquire-interrupted") {
            const auto limit = scenario == "repeated-interrupted" ? 3u : 1u;
            if (interruptions < limit) {
                if (scenario == "reply-before-interrupted" && interruptions == 0) deliver();
                ++interruptions;
                // Return KERN_ABORTED without consuming a semaphore token,
                // exactly as the production dtape_semaphore_down_simple API.
                return false;
            }
        }
        if (it->second.count == 0) deliver();
    }
    require(it->second.count > 0, "wait had no token and no controlled reply");
    --it->second.count; return true;
}

extern "C" void fixture_send(DarlingServer::Server*, Message&& message)
    asm("__wrap__ZN13DarlingServer6Server11sendMessageEONS_7MessageE");
extern "C" void fixture_send(DarlingServer::Server*, Message&& message) {
    auto* header = reinterpret_cast<dserver_s2c_callhdr_t*>(message.data().data());
    require(header->call_number == dserver_callnum_s2c, "unexpected non-S2C transport");
    require(header->s2c_number == dserver_s2c_msgnum_mmap ||
            header->s2c_number == dserver_s2c_msgnum_munmap, "unexpected S2C operation");
    ++sent; requests.push_back(header->s2c_number);
    if (sent == 2 && scenario != "normal" && scenario != "acquire-interrupted" &&
        requests.size() == 2) {
        // A canceled client-side wait cannot cancel the already sent request.
        // Release both replies now; old code leaves the first one pending and
        // the actual production reply handler rejects the second reply.
        deliver(); deliver();
    }
}

extern "C" {
void fixture_install_hooks();
dtape_thread_t* fixture_create_thread(void*);
void* fixture_current_context() { return Thread::currentThread().get(); }
void fixture_suspend(void* context, dtape_thread_continuation_callback_f continuation,
                     void* argument, libsimple_lock_t* unlock) {
    auto* thread = static_cast<Thread*>(context);
    if (continuation) thread->suspend([=] { continuation(argument); }, unlock);
    else thread->suspend(nullptr, unlock);
}
void fixture_resume(void* context) { static_cast<Thread*>(context)->resume(); }
void fixture_complete_continuation() { std::abort(); }
dtape_task_t* __wrap_dtape_task_create(dtape_task_t*, uint32_t, void* context,
                                     dserver_rpc_architecture_t) {
    return reinterpret_cast<dtape_task_t*>(context);
}
dtape_thread_t* __wrap_dtape_thread_create(dtape_task_t*, uint64_t, void* context) {
    return fixture_create_thread(context);
}
void __wrap_dtape_task_set_process_generation(dtape_task_t*, dtape_eternal_id_t, uint32_t) {}
void __wrap_dtape_task_set_audit_identity(dtape_task_t*, uint32_t, uint32_t) {}
void __wrap_dtape_thread_dying(dtape_thread_t*) {}
}
extern "C" void schedule(DarlingServer::Server*, std::shared_ptr<Thread> thread)
    asm("__wrap__ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE");
extern "C" void schedule(DarlingServer::Server*, std::shared_ptr<Thread> thread) {
    runnable.push_back(std::move(thread));
}

class IdleCall final: public Call {
public:
    IdleCall(std::shared_ptr<Thread> thread, dserver_rpc_callhdr_t* header):
        Call(thread, Address{}, header) {}
    Number number() const override { return Number::Invalid; }
    void processCall() override { std::abort(); }
};

int main(int argc, char** argv) {
    require(argc == 3, "usage: fixture CASE PRIVATE_PREFIX"); scenario = argv[1];
    new Server(argv[2]); fixture_install_hooks();
    auto process = std::make_shared<Process>(getpid(), getpid(), Process::Architecture::x86_64);
    require(processRegistry().registerEntry(process), "process registry fixture failed");
    target = std::make_shared<Thread>(process, getpid()); target->registerWithProcess();
    require(threadRegistry().registerEntry(target), "thread registry fixture failed");
    dserver_rpc_callhdr_t callHeader{};
    DTapeHooks::active(*target, std::make_shared<IdleCall>(target, &callHeader));
    caller = std::make_shared<Thread>(Thread::KernelThreadConstructorTag{});
    caller->registerWithProcess();
    unsigned completed = 0;
    caller->startKernelThread([&] {
        int mapError = 0; const auto address = DTapeHooks::mmap(*target, mapError);
        const bool beforeSend = scenario == "acquire-interrupted";
        if (beforeSend) require(address == uintptr_t(MAP_FAILED) && mapError == EINTR && sent == 0,
                                "pre-send interruption did not cancel cleanly");
        // Preserve the old-source failure until its second real reply ingestion
        // so the negative control observes the same duplicate-pending failure.
        const bool correctMap = beforeSend || (address == expectedAddress && mapError == 0);
        int unmapError = 0;
        require(DTapeHooks::munmap(*target, unmapError) == 0 && unmapError == 0,
                "munmap transaction failed");
        require(correctMap, "completed mmap was reported interrupted instead of consumed");
        require(!DTapeHooks::pending(*target) && requests.empty(), "transaction left stale reply");
        require(semaphores.at(DTapeHooks::perform(*target)).count == 1 &&
                semaphores.at(DTapeHooks::reply(*target)).count == 0,
                "transaction leaked semaphore token");
        ++completed;
    });
    require(runnable.size() == 1, "caller not scheduled");
    runnable.front()->doWork(); runnable.pop_front();
    require(completed == 1 && runnable.empty(), "transaction caller did not complete");
    std::printf("PASS %s sent=%u received=%u interruptions=%u reply_waits=%u\n",
                scenario.c_str(), sent, received, interruptions, replyWaits);
    std::fflush(nullptr); std::_Exit(0);
}
