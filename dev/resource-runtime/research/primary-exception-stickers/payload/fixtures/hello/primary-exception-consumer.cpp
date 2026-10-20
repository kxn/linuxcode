#include "primary-exception-fixture.h"
#include "cxa_exception.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <pthread.h>
#include <typeinfo>

static std::atomic<unsigned> checks(0);
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL %d %s\n",__LINE__,#x); std::exit(2); } } while(0)
using namespace __cxxabiv1;

static void one(unsigned code) {
    void* returned = nullptr;
    void* object = primary_create_unowned(code, &returned);
    auto* header = static_cast<__cxa_exception*>(returned);
    CHECK(header + 1 == object);
    CHECK(header->referenceCount == 0);
    CHECK(header->exceptionType == &typeid(PrimaryError));
    CHECK(header->exceptionDestructor == primary_destroy);
    CHECK(header->terminateHandler == std::get_terminate());
    CHECK(header->unexpectedHandler == std::get_unexpected());
    CHECK(header->handlerCount == 0);
    CHECK(header->unwindHeader.exception_cleanup);
    uint64_t exception_class;
    std::memcpy(&exception_class, &header->unwindHeader.exception_class, sizeof(exception_class));
    CHECK(exception_class == kOurExceptionClass);
    CHECK(__cxa_uncaught_exceptions() == 0);
    __cxa_increment_exception_refcount(object);
    CHECK(header->referenceCount == 1);
    unsigned before = primary_destroyed();
    std::exception_ptr saved;
    bool caught = false;
    try {
        try { __cxa_rethrow_primary_exception(object); }
        catch (const PrimaryError& error) {
            CHECK(&error == object);
            CHECK(error.code == static_cast<int>(code));
            CHECK(typeid(error) == typeid(PrimaryError));
            CHECK(!std::strcmp(error.what(), "primary exception fixture"));
            saved = std::current_exception();
            CHECK(saved != nullptr);
            throw;
        }
    } catch (const PrimaryError& error) {
        CHECK(&error == object);
        caught = true;
    }
    CHECK(caught && __cxa_uncaught_exceptions() == 0);
    CHECK(primary_destroyed() == before);
    auto copy = saved;
    __cxa_decrement_exception_refcount(object);
    saved = nullptr;
    CHECK(primary_destroyed() == before);
    try { std::rethrow_exception(copy); }
    catch (const PrimaryError& error) { CHECK(&error == object && error.code == static_cast<int>(code)); }
    copy = nullptr;
    CHECK(primary_destroyed() == before + 1);
}

struct Worker { const std::exception_ptr* pointer; const void* object; };
static void* worker(void* opaque) {
    auto& work = *static_cast<Worker*>(opaque);
    CHECK(__cxa_uncaught_exceptions() == 0);
    for (unsigned i = 0; i != 256; ++i) {
        auto copy = *work.pointer;
        bool caught = false;
        try { std::rethrow_exception(copy); }
        catch (const PrimaryError& error) {
            caught = true;
            CHECK(&error == work.object && error.code == 731);
            CHECK(typeid(error) == typeid(PrimaryError));
        }
        CHECK(caught && __cxa_uncaught_exceptions() == 0);
    }
    return nullptr;
}

int main(int argc, char** argv) {
    CHECK(argc == 2);
    one(0);
    auto init = dlsym(RTLD_DEFAULT, "__cxa_init_primary_exception");
    CHECK(init);
    Dl_info owner;
    CHECK(dladdr(init, &owner));
    CHECK(std::strstr(owner.dli_fname, argv[1]));
    std::printf("PRIMARY_EXCEPTION_OWNER %s\n", owner.dli_fname);
    for (unsigned i = 1; i != 128; ++i) one(i);
    CHECK(primary_destroyed() == 128);
    void* returned;
    void* object = primary_create_unowned(731, &returned);
    __cxa_increment_exception_refcount(object);
    std::exception_ptr shared;
    try { __cxa_rethrow_primary_exception(object); }
    catch (...) { shared = std::current_exception(); }
    __cxa_decrement_exception_refcount(object);
    Worker work{&shared, object};
    pthread_t threads[4];
    for (auto& thread : threads) CHECK(pthread_create(&thread, nullptr, worker, &work) == 0);
    for (auto& thread : threads) CHECK(pthread_join(thread, nullptr) == 0);
    CHECK(primary_destroyed() == 128);
    shared = nullptr;
    CHECK(primary_destroyed() == 129);
    // Exercise the real unwind cleanup callback without initiating a throw.
    object = primary_create_unowned(9, &returned);
    auto* header = static_cast<__cxa_exception*>(returned);
    __cxa_increment_exception_refcount(object);
    header->unwindHeader.exception_cleanup(_URC_FOREIGN_EXCEPTION_CAUGHT, &header->unwindHeader);
    CHECK(primary_destroyed() == 130);
    // The existing throw path must still initialize and destroy ordinary errors.
    try { throw PrimaryError(43); }
    catch (const PrimaryError& error) { CHECK(error.code == 43); }
    CHECK(primary_destroyed() == 131);
    std::printf("PRIMARY_EXCEPTION_ABI_REFCOUNT_CROSS_DSO_RETHROW_CLEANUP_AND_4_THREADS_OK checks=%u\n", checks.load());
}
