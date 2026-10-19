#include <memory_resource>
#include <typeinfo>
extern "C" std::pmr::memory_resource* pmr_make_resource();
extern "C" const std::type_info* pmr_base_type();
extern "C" const std::type_info* pmr_dynamic_type();
extern "C" bool pmr_is_derived(std::pmr::memory_resource*);
extern "C" void pmr_force_failure(bool);
extern "C" unsigned pmr_allocations();
extern "C" unsigned pmr_deallocations();
extern "C" unsigned pmr_destructions();
