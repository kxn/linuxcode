/* Exact binary powers are an integer oracle, including every subnormal power.
 * Both routines are called dynamically; no compiler-folded math is tested. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
#include <fenv.h>

typedef double (*function_t)(double);
static uint64_t ordered(double value) {
    uint64_t bits; memcpy(&bits,&value,sizeof(bits));
    return bits>>63 ? ~bits : bits|(1ULL<<63);
}
static unsigned family_cases(function_t actual,function_t reference,void* candidate,void* original) {
    unsigned failures=0,cases=0;uint64_t max_ulp=0;
    const int modes[]={FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO};
    for (unsigned mode=0;mode<4;++mode) {
        if (fesetround(modes[mode])) return 1;
        uint64_t state=0x1829467a965bcde7ULL;
        for (unsigned i=0;i<520;++i) {
            state^=state<<13;state^=state>>7;state^=state<<17;
            uint64_t bits=(state&0x7fffffffffffffffULL);
            if (bits>=0x7ff0000000000000ULL) bits^=0x0010000000000000ULL;
            if (i<8) { const uint64_t edges[]={1,3,0xfffffffffffffULL,0x10000000000001ULL,
                 0x3fefffffffffffffULL,0x3ff0000000000001ULL,0x7fefffffffffffffULL,0x3ff8000000000000ULL};bits=edges[i]; }
            double input;memcpy(&input,&bits,sizeof(input));
            double result=actual(input),expected=reference(input);
            uint64_t a=ordered(result),b=ordered(expected),distance=a>b?a-b:b-a;
            if (distance>max_ulp) max_ulp=distance;
            if (distance>2) { if(failures<5)printf("MAINLINE_DIFFERENCE mode=%u input=%a actual=%a reference=%a ulp=%llu\n",mode,input,result,expected,(unsigned long long)distance);++failures; }
            ++cases;
        }
    }
    fesetround(FE_TONEAREST);
    float (*actual_f)(float)=(float(*)(float))dlsym(candidate,"log2f");
    long double (*actual_l)(long double)=(long double(*)(long double))dlsym(candidate,"log2l");
    if (!actual_f || !actual_l) return 1;
    for(int exponent=-149;exponent<=127;++exponent) {
        float input=ldexpf(1.0f,exponent);if(actual_f(input)!=exponent)++failures;++cases;
    }
    for(int exponent=-16445;exponent<=16383;++exponent) {
        long double input=ldexpl(1.0L,exponent);if(actual_l(input)!=exponent)++failures;++cases;
    }
    const uint64_t special_bits[]={0,0x8000000000000000ULL,0xbff0000000000000ULL,
         0x7ff0000000000000ULL,0x7ff8000000000001ULL,0x7ff0000000000001ULL};
    for(unsigned i=0;i<6;++i) {
        double input;memcpy(&input,&special_bits[i],sizeof(input));
        feclearexcept(FE_ALL_EXCEPT);double a=actual(input);int actual_flags=fetestexcept(FE_ALL_EXCEPT);
        feclearexcept(FE_ALL_EXCEPT);double b=reference(input);int reference_flags=fetestexcept(FE_ALL_EXCEPT);
        printf("SPECIAL_RECORD input_bits=%016llx actual=%a reference=%a actual_flags=%x reference_flags=%x\n",(unsigned long long)special_bits[i],a,b,actual_flags,reference_flags);
        ++cases;
    }
    function_t off=(function_t)dlsym(candidate,"log2$fenv_access_off");
    if (!off || off(16384.0)!=14.0)++failures;
    printf("LOG2_FAMILY cases=%u failures=%u mainline_max_ulp=%llu special_semantics_recorded_not_claimed_equal=1\n",cases,failures,(unsigned long long)max_ulp);
    return failures;
}
int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) return 2;
    void* original = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    void* candidate = strcmp(argv[2], "default") ? dlopen(argv[2], RTLD_NOW | RTLD_LOCAL) : RTLD_DEFAULT;
    if (!original || (strcmp(argv[2], "default") && !candidate)) {
        printf("DLOPEN_ERROR %s\n", dlerror()); return 3;
    }
    function_t reference = (function_t)dlsym(original, "log2");
    function_t actual = (function_t)dlsym(candidate, "log2");
    if (!reference || !actual) return 4;
    Dl_info info;
    if (dladdr((void*)actual, &info)) printf("ACTUAL_OWNER %s\n", info.dli_fname);
    if (dladdr((void*)reference, &info)) printf("REFERENCE_OWNER %s\n", info.dli_fname);
    unsigned failures = 0, reference_failures = 0;
    for (int exponent = -1074; exponent <= 1023; ++exponent) {
        uint64_t bits = exponent >= -1022 ? (uint64_t)(exponent + 1023) << 52 : 1ULL << (exponent + 1074);
        double input; memcpy(&input, &bits, sizeof(input));
        double result = actual(input), expected = reference(input);
        if (expected != exponent) ++reference_failures;
        if (result != exponent) {
            if (failures < 12) printf("INEXACT_POWER exponent=%d input=%a actual=%a reference=%a\n", exponent, input, result, expected);
            ++failures;
        }
        if (exponent == 14) printf("LINKER_CASE input=16384 actual=%a reference=%a actual_truncated=%d reference_truncated=%d\n", result, expected, (int)result, (int)expected);
    }
    printf("LOG2_POWERS cases=2098 failures=%u reference_failures=%u\n", failures, reference_failures);
    if (argc==4 && family_cases(actual,reference,candidate,original))return 6;
    return reference_failures ? 5 : failures ? 1 : 0;
}
