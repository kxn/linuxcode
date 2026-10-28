// Owned ordinary exceptions. No invalid memory access, custom personality,
// runtime replacement or certificate/account operations.
#import <Foundation/Foundation.h>
#include <stdio.h>
static unsigned cpp_destructors, objc_destructors, checks;
struct Lifetime {
    unsigned& count;
    explicit Lifetime(unsigned& value) : count(value) {}
    ~Lifetime() { ++count; }
};
struct Expected { int value; };
__attribute__((noinline)) static void cpp_throw() {
    Lifetime lifetime(cpp_destructors); throw Expected{37};
}
__attribute__((noinline)) static void objc_throw() {
    Lifetime lifetime(objc_destructors);
    @throw [NSException exceptionWithName:@"LinuxcodeOwnedUnwind" reason:@"owned public API fixture" userInfo:nil];
}
static bool check(bool condition, const char* name) {
    if (!condition) { printf("UNWIND_EXCEPTION_FAIL %s\n", name); return false; }
    ++checks; printf("UNWIND_EXCEPTION_CHECK %s\n", name); return true;
}
int main() {
    setbuf(stdout, NULL);
    @autoreleasepool {
        bool caught_cpp = false;
        try { cpp_throw(); } catch (const Expected& error) { caught_cpp = error.value == 37; }
        if (!check(caught_cpp, "cpp-typed-catch")) return 1;
        if (!check(cpp_destructors == 1, "cpp-stack-destructor")) return 1;
        bool caught_objc = false;
        @try { objc_throw(); }
        @catch (NSException* error) { caught_objc = [error.name isEqualToString:@"LinuxcodeOwnedUnwind"]; }
        if (!check(caught_objc, "foundation-nsexception-catch")) return 1;
        if (!check(objc_destructors == 1, "objc-exception-cpp-stack-destructor")) return 1;
        printf("UNWIND_CPP_AND_FOUNDATION_EXCEPTION_DESTRUCTORS_OK checks=%u\n", checks);
    }
    return 0;
}
