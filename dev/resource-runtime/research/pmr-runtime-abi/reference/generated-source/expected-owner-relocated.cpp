#include <expected>
#include <exception>
#include <typeinfo>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include "expected-access-fixture.h"
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);std::exit(1);}}while(0)
static void check_base(const std::exception& error){
    CHECK(!std::strcmp(error.what(),"bad access to std::expected"));
    CHECK(dynamic_cast<const std::bad_expected_access<void>*>(&error));
}
int main(){
    CHECK(sizeof(std::bad_expected_access<void>)==sizeof(void*));
    CHECK(alignof(std::bad_expected_access<void>)==alignof(void*));
    void *library=dlopen("/usr/lib/libc++.1.dylib",RTLD_LAZY|RTLD_LOCAL);CHECK(library);
    auto *info=dlsym(library,"_ZTINSt3__119bad_expected_accessIvEE");CHECK(info==&typeid(std::bad_expected_access<void>));
    auto *name=static_cast<const char*>(dlsym(library,"_ZTSNSt3__119bad_expected_accessIvEE"));CHECK(name);
    CHECK(!std::strcmp(name,"NSt3__119bad_expected_accessIvEE"));
    CHECK(!std::strcmp(typeid(std::bad_expected_access<void>).name(),name));
    void *what=dlsym(library,"_ZNKSt3__119bad_expected_accessIvE4whatEv");CHECK(what);
    auto **vtable=static_cast<void**>(dlsym(library,"_ZTVNSt3__119bad_expected_accessIvEE"));CHECK(vtable);CHECK(!vtable[0]);CHECK(vtable[1]==info);CHECK(vtable[2]&&vtable[3]);CHECK(vtable[4]==what);
    Dl_info owner;CHECK(dladdr(what,&owner));CHECK(std::strstr(owner.dli_fname,"/runtime/pmr-key-function-v1/libraries/libc++.1.dylib"));
    for(unsigned i=0;i<128;i++){
        CHECK(expected_valid_value()==42);CHECK(expected_live_payloads()==0);
        bool caught=false;
        try{expected_throw_int();}catch(const std::bad_expected_access<int>& error){caught=true;CHECK(error.error()==73);check_base(error);CHECK(typeid(error)==typeid(std::bad_expected_access<int>));}
        CHECK(caught);
        caught=false;
        try{expected_throw_payload();}catch(const std::bad_expected_access<ExpectedPayload>& error){caught=true;CHECK(error.error().code==91);CHECK(error.error().marker==0xfedcba9876543210ULL);check_base(error);CHECK(expected_live_payloads()==1);}
        CHECK(caught);CHECK(expected_live_payloads()==0);
        caught=false;
        try{expected_throw_int();}catch(const std::bad_expected_access<void>& error){caught=true;check_base(error);CHECK(static_cast<const std::exception*>(&error)!=nullptr);}
        CHECK(caught);
        {
            auto pointer=expected_saved_payload();CHECK(pointer!=nullptr);CHECK(expected_live_payloads()==1);auto copy=pointer;pointer=nullptr;CHECK(expected_live_payloads()==1);
            try{std::rethrow_exception(copy);}catch(const std::exception& error){check_base(error);auto *typed=dynamic_cast<const std::bad_expected_access<ExpectedPayload>*>(&error);CHECK(typed&&typed->error().code==91);}
        }
        CHECK(expected_live_payloads()==0);
    }
    std::printf("EXPECTED_ACCESS_SOURCE_RTTI_VTABLE_CROSS_DYLIB_THROW_CATCH_RETHROW_AND_LIFETIME_OK checks=%u iterations=128\n",checks);
}
