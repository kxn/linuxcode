#include "pmr-key-fixture.h"
#include <cstdlib>
#include <new>
static unsigned allocations, deallocations, destructions;
static bool fail;
class TestResource final : public std::pmr::memory_resource {
    void* do_allocate(std::size_t bytes, std::size_t alignment) override {
        void* result = nullptr;
        if (fail || posix_memalign(&result, alignment < sizeof(void*) ? sizeof(void*) : alignment,
                                  bytes ? bytes : 1)) throw std::bad_alloc();
        ++allocations;
        return result;
    }
    void do_deallocate(void* address, std::size_t, std::size_t) override {
        ++deallocations;
        std::free(address);
    }
    bool do_is_equal(const std::pmr::memory_resource& other) const noexcept override {
        return this == &other;
    }
public:
    ~TestResource() override { ++destructions; }
};
extern "C" std::pmr::memory_resource* pmr_make_resource() { return new TestResource; }
extern "C" const std::type_info* pmr_base_type() { return &typeid(std::pmr::memory_resource); }
extern "C" const std::type_info* pmr_dynamic_type() { return &typeid(TestResource); }
extern "C" bool pmr_is_derived(std::pmr::memory_resource* value) { return dynamic_cast<TestResource*>(value); }
extern "C" void pmr_force_failure(bool value) { fail = value; }
extern "C" unsigned pmr_allocations() { return allocations; }
extern "C" unsigned pmr_deallocations() { return deallocations; }
extern "C" unsigned pmr_destructions() { return destructions; }
