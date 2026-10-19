/* Differential ABI test of the deferred original token entry points.
 * This tests forwarding/results, not macOS SIP enforcement on Linux. */
#include <assert.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
typedef uint32_t (*make_fn)(pid_t,unsigned);
typedef bool (*verify_fn)(uint32_t,unsigned);
int main(void) {
    setbuf(stdout,NULL);
    make_fn forward_make = dlsym(RTLD_DEFAULT,"rootless_trusted_by_self_token");
    verify_fn forward_verify = dlsym(RTLD_DEFAULT,"rootless_verify_trusted_by_self_token");
    assert(forward_make && forward_verify);
    Dl_info owner;
    assert(dladdr((void *)forward_make,&owner) && strstr(owner.dli_fname,"libDarlingRootlessToken.dylib"));
    assert(dladdr((void *)forward_verify,&owner) && strstr(owner.dli_fname,"libDarlingRootlessToken.dylib"));
    void *native = dlopen("/Volumes/SystemRoot/workspace/runtime/foundation-native-library-stage/libDarlingNativeSandbox.dylib",RTLD_LAZY|RTLD_LOCAL);
    assert(native);
    make_fn original_make = dlsym(native,"rootless_trusted_by_self_token");
    verify_fn original_verify = dlsym(native,"rootless_verify_trusted_by_self_token");
    assert(original_make && original_verify);
    assert(dladdr((void *)original_make,&owner) && strstr(owner.dli_fname,"/foundation-native-library-stage/libDarlingNativeSandbox.dylib"));
    unsigned cases=0;
    const unsigned bits[] = {0,1,3,7,30};
    for (unsigned n=0;n<5;++n) {
        uint32_t direct = original_make(getpid(),bits[n]);
        uint32_t forwarded = forward_make(getpid(),bits[n]);
        assert(forwarded==direct && (direct&UINT32_C(0x80000000)));
        for(unsigned bit=0;bit<31;++bit) {
            bool expected = (direct&(UINT32_C(1)<<bit))!=0;
            assert(original_verify(direct,bit)==expected);
            assert(forward_verify(direct,bit)==expected);
            cases++;
        }
        printf("NATIVE_ROOTLESS_TOKEN_RESULT %u 0x%08x\n",bits[n],direct);
    }
    printf("NATIVE_ROOTLESS_TOKEN_DEFERRED_FORWARDING_AND_REAL_RESULT_BITS_OK %u\n",cases);
    return 0;
}
