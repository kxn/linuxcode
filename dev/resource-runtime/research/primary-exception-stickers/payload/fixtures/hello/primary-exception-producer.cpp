#include "primary-exception-fixture.h"
#include <atomic>
#include <new>
#include <typeinfo>
#include <cxxabi.h>

static std::atomic<unsigned> destroyed(0);
PrimaryError::PrimaryError(int value) : code(value) {}
PrimaryError::~PrimaryError() noexcept { ++destroyed; }
const char* PrimaryError::what() const noexcept { return "primary exception fixture"; }
extern "C" void primary_destroy(void* object) {
    static_cast<PrimaryError*>(object)->~PrimaryError();
}
extern "C" unsigned primary_destroyed() { return destroyed.load(); }
extern "C" void* primary_create_unowned(int code, void** header) {
    void* object = __cxxabiv1::__cxa_allocate_exception(sizeof(PrimaryError));
    ::new (object) PrimaryError(code);
    *header = __cxxabiv1::__cxa_init_primary_exception(
        object, const_cast<std::type_info*>(&typeid(PrimaryError)), primary_destroy);
    return object;
}
