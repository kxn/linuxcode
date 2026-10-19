#include "pmr-key-fixture.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <new>
static unsigned checks;
#define CHECK(value) do { ++checks; if (!(value)) { std::fprintf(stderr,"PMR_FAIL %d %s\n",__LINE__,#value); std::exit(1); } } while(0)
int main() {
    std::setbuf(stdout, nullptr);
    std::puts("PMR_NATIVE_TEST_BEGIN");
    CHECK(sizeof(std::pmr::memory_resource) == sizeof(void*));
    CHECK(alignof(std::pmr::memory_resource) == alignof(void*));
    auto* info = dlsym(RTLD_DEFAULT, "_ZTINSt3__13pmr15memory_resourceE");
    CHECK(info == &typeid(std::pmr::memory_resource));
    CHECK(info == pmr_base_type());
    auto* name = static_cast<const char*>(dlsym(RTLD_DEFAULT,"_ZTSNSt3__13pmr15memory_resourceE"));
    CHECK(name && !std::strcmp(name,"NSt3__13pmr15memory_resourceE"));
    CHECK(!std::strcmp(typeid(std::pmr::memory_resource).name(),name));
    auto** table = static_cast<void**>(dlsym(RTLD_DEFAULT,"_ZTVNSt3__13pmr15memory_resourceE"));
    CHECK(table && !table[0] && table[1] == info);
    CHECK(table[2] == dlsym(RTLD_DEFAULT,"_ZNSt3__13pmr15memory_resourceD1Ev"));
    CHECK(table[3] == dlsym(RTLD_DEFAULT,"_ZNSt3__13pmr15memory_resourceD0Ev"));
    Dl_info owner;
    CHECK(dladdr(info,&owner) && owner.dli_fname);
    std::printf("PMR_CANONICAL_TYPE_OWNER %s\n",owner.dli_fname);
    auto* first = pmr_make_resource();
    auto* other = pmr_make_resource();
    CHECK(first && other && first != other);
    CHECK(pmr_is_derived(first) && pmr_is_derived(other));
    CHECK(&typeid(*first) == pmr_dynamic_type());
    CHECK(dynamic_cast<void*>(first) == first);
    CHECK(first->is_equal(*first) && !first->is_equal(*other));
    for (unsigned round=0; round<128; ++round) {
        std::size_t alignment = std::size_t(8) << (round%10);
        std::size_t bytes = round%11 ? round*37 : 0;
        void* address = first->allocate(bytes,alignment);
        CHECK(address && reinterpret_cast<std::uintptr_t>(address)%alignment == 0);
        std::memset(address,int(round),bytes);
        for(std::size_t i=0;i<bytes;i++) CHECK(static_cast<unsigned char*>(address)[i] == static_cast<unsigned char>(round));
        first->deallocate(address,bytes,alignment);
    }
    CHECK(pmr_allocations()==128 && pmr_deallocations()==128);
    pmr_force_failure(true);
    bool caught = false;
    try { (void)first->allocate(64,16); }
    catch(const std::bad_alloc&) { caught=true; }
    CHECK(caught && pmr_allocations()==128 && pmr_deallocations()==128);
    pmr_force_failure(false);
    delete first;
    delete other;
    CHECK(pmr_destructions()==2);
    std::printf("PMR_SDK_KEY_FUNCTION_RTTI_VTABLE_CROSS_DSO_VIRTUAL_ALLOC_ALIGNMENT_FAILURE_AND_DESTRUCTION_OK checks=%u allocations=128 destructions=2\n",checks);
}
