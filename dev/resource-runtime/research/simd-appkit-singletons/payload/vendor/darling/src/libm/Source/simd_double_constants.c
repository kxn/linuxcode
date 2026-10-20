/* Public SDK ABI: three 32-byte columns; the matrix has 16-byte alignment. */
typedef double darling_simd_double3 __attribute__((ext_vector_type(3), aligned(16)));
typedef struct { darling_simd_double3 columns[3]; } darling_simd_double3x3;
_Static_assert(sizeof(darling_simd_double3x3) == 96, "SIMD double3x3 size");
_Static_assert(_Alignof(darling_simd_double3x3) == 16, "SIMD double3x3 alignment");
const darling_simd_double3x3 matrix_identity_double3x3 = {
    .columns = {{1., 0., 0.}, {0., 1., 0.}, {0., 0., 1.}}
};

typedef double darling_simd_double4 __attribute__((ext_vector_type(4), aligned(16)));
typedef struct { darling_simd_double4 columns[4]; } darling_simd_double4x4;
_Static_assert(sizeof(darling_simd_double4x4) == 128, "SIMD double4x4 size");
_Static_assert(_Alignof(darling_simd_double4x4) == 16, "SIMD double4x4 alignment");
const darling_simd_double4x4 matrix_identity_double4x4 = {
    .columns = {{1., 0., 0., 0.}, {0., 1., 0., 0.},
                {0., 0., 1., 0.}, {0., 0., 0., 1.}}
};
