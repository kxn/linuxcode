#include <simd/simd.h>
#include <assert.h>
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "oracle.h"

typedef simd_float4 (*unary_fn)(simd_float4);
typedef simd_float4 (*binary_fn)(simd_float4, simd_float4);
static void *original(const char *name) {
    void *function = dlsym(RTLD_DEFAULT, name);
    Dl_info owner;
    assert(function && dladdr(function, &owner));
    assert(strstr(owner.dli_fname, "/coregraphics-native-") &&
           strstr(owner.dli_fname, "/libDarlingNativeSIMDMath.dylib"));
    return function;
}
static uint32_t float_bits(float x) {
    uint32_t result; memcpy(&result, &x, sizeof(result)); return result;
}
int main(void) {
    setbuf(stdout, NULL);
    assert(!getenv("DISPLAY") && !getenv("WAYLAND_DISPLAY") && !getenv("XAUTHORITY"));
    _Static_assert(sizeof(simd_float3x3) == 48, "SDK matrix size");
    _Static_assert(_Alignof(simd_float3x3) == 16, "SDK matrix alignment");
    simd_float3x3 (*inverse)(simd_float3x3) = original("__invert_f3");
    for (unsigned n = 0; n < sizeof(matrices)/sizeof(*matrices); ++n) {
        simd_float3x3 input = {0};
        for (unsigned row = 0; row < 3; ++row)
            for (unsigned col = 0; col < 3; ++col)
                input.columns[col][row] = matrices[n].input[row*3+col];
        simd_float3x3 output = inverse(input);
        for (unsigned row = 0; row < 3; ++row)
            for (unsigned col = 0; col < 3; ++col) {
                double expected = matrices[n].inverse[row*3+col];
                assert(fabs(output.columns[col][row]-expected) <= 2e-6*fmax(fabs(expected),1e-10));
                double residual = 0;
                for (unsigned k = 0; k < 3; ++k)
                    residual += (double)input.columns[k][row]*output.columns[col][k];
                assert(fabs(residual-(row==col)) < 3e-6);
            }
    }
    printf("ORIGINAL_SIMD_MATH_MATRIX_ORACLE_OK %lu\n", sizeof(matrices)/sizeof(*matrices));
    const char *names[] = {"_simd_exp_f4", "_simd_exp2_f4", "_simd_log_f4",
                          "_simd_log2_f4", "_simd_sin_f4", "_simd_pow_f4"};
    void *functions[6];
    for (unsigned n=0;n<6;++n) functions[n]=original(names[n]);
    unsigned lanes=0, zero_differences=0;
    for (unsigned n=0;n<sizeof(vectors)/sizeof(*vectors);++n) {
        simd_float4 x, y;
        for (unsigned lane=0;lane<4;++lane) {x[lane]=vectors[n].x[lane]; y[lane]=vectors[n].y[lane];}
        simd_float4 actual = vectors[n].function==5
            ? ((binary_fn)functions[5])(x,y)
            : ((unary_fn)functions[vectors[n].function])(x);
        for (unsigned lane=0;lane<4;++lane,++lanes) {
            float expected=vectors[n].expected[lane], value=actual[lane];
            if (isnan(expected)) assert(isnan(value));
            else if (isinf(expected)) assert(isinf(value) && signbit(value)==signbit(expected));
            else if (expected==0) {
                if (float_bits(value)!=float_bits(expected)) {fprintf(stderr,"zero mismatch vector %u lane %u function %s input %.9g: 0x%08x != 0x%08x\n",n,lane,names[vectors[n].function],x[lane],float_bits(value),float_bits(expected));assert(value==0);++zero_differences;}
            }
            else {
                assert(isfinite(value) && signbit(value)==signbit(expected));
                uint32_t a=float_bits(value),b=float_bits(expected),ulps=a>b?a-b:b-a;
                if (ulps>8) {fprintf(stderr,"vector %u lane %u function %s: %.9g != %.9g (%u ulps)\n",n,lane,names[vectors[n].function],value,expected,ulps);abort();}
            }
        }
    }
    printf("ORIGINAL_SIMD_MATH_VECTOR_ORACLE_OK %u\n",lanes);
    printf("ORIGINAL_SIMD_MATH_SIGNED_ZERO_DIFFERENCES %u\n",zero_differences);
    puts("ORIGINAL_SIMD_MATH_OWNERS_AND_HEADLESS_OK");
    return 0;
}
