/* Real C signal entry, waitq operations, block/unblock, C++ ucontext and
 * scheduler. Opaque task construction and enqueue boundary are controlled. */
#include <darlingserver/thread.hpp>
#include <darlingserver/server.hpp>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <map>
#include <string>
using namespace DarlingServer;
static std::deque<std::shared_ptr<Thread>> queued;
extern "C" {
void fixture_install_hooks();
dtape_thread_t *fixture_create_thread(void *);
int fixture_sigexc_case(int);
int fixture_observed_state();
int fixture_observed_result();
int fixture_observed_linked();
unsigned fixture_resume_hooks();
void *fixture_current_context() { return Thread::currentThread().get(); }
void fixture_suspend(void *context, dtape_thread_continuation_callback_f continuation,
                     void *argument, libsimple_lock_t *unlock) {
    auto *thread = static_cast<Thread*>(context);
    if (continuation) thread->suspend([=] { continuation(argument); }, unlock);
    else thread->suspend(nullptr, unlock);
}
void fixture_resume(void *context) { static_cast<Thread*>(context)->resume(); }
dtape_task_t *__wrap_dtape_task_create(dtape_task_t*, uint32_t, void *context, dserver_rpc_architecture_t) {
    return reinterpret_cast<dtape_task_t*>(context);
}
dtape_thread_t *__wrap_dtape_thread_create(dtape_task_t*, uint64_t, void *context) {
    return fixture_create_thread(context);
}
void __wrap_dtape_task_set_process_generation(dtape_task_t*, dtape_eternal_id_t, uint32_t) {}
void __wrap_dtape_thread_dying(dtape_thread_t*) {}
}
extern "C" void schedule(Server*, std::shared_ptr<Thread> thread)
    asm("__wrap__ZN13DarlingServer6Server14scheduleThreadESt10shared_ptrINS_6ThreadEE");
extern "C" void schedule(Server*, std::shared_ptr<Thread> thread) { queued.push_back(std::move(thread)); }
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    const std::string name=argv[1];
    const std::map<std::string,int> cases={{"awaken-before-interrupt",0},{"interrupt-before-awaken",1},
                                        {"no-wait",2},{"uninterruptible",3}};
    if (!cases.count(name)) return 2;
    new Server(argv[2]); fixture_install_hooks();
    auto target=std::make_shared<Thread>(Thread::KernelThreadConstructorTag{});
    target->registerWithProcess();
    int result=-1;
    target->startKernelThread([&] { result=fixture_sigexc_case(cases.at(name)); });
    if (queued.size()!=1) return 3;
    queued.front()->doWork(); queued.pop_front();
    std::printf("%s %s code=%d state=%d result=%d linked=%d resume_hooks=%u\n",
                result==0?"PASS":"FAIL",name.c_str(),result,fixture_observed_state(),
                fixture_observed_result(),fixture_observed_linked(),fixture_resume_hooks());
    std::fflush(nullptr); std::_Exit(result==0?0:1);
}
