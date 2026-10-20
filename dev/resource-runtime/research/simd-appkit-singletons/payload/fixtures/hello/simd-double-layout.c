#include <simd/types.h>
#include "../../vendor/darling/src/libm/Source/simd_double_constants.c"

_Static_assert(sizeof(darling_simd_double4x4)==sizeof(simd_double4x4), "SDK matrix size");
_Static_assert(_Alignof(darling_simd_double4x4)==_Alignof(simd_double4x4), "SDK matrix alignment");
_Static_assert(__builtin_offsetof(darling_simd_double4x4,columns[3])==
               __builtin_offsetof(simd_double4x4,columns[3]), "SDK column stride");
_Static_assert(__builtin_types_compatible_p(darling_simd_double4,simd_double4), "SDK vector type");
_Static_assert(sizeof(darling_simd_double3x3)==sizeof(simd_double3x3), "Existing SDK matrix size");
_Static_assert(_Alignof(darling_simd_double3x3)==_Alignof(simd_double3x3), "Existing SDK alignment");
