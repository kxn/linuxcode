#include <simd/types.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

extern const simd_double4x4 matrix_identity_double4x4;
extern const simd_double3x3 matrix_identity_double3x3;
_Static_assert(sizeof(simd_double4x4)==128, "SDK size");
_Static_assert(_Alignof(simd_double4x4)==16, "SDK alignment");

int main(int argc,char **argv) {
    if (argc!=2) return 10;
    const double expected4[16]={1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};
    const double expected3[12]={1,0,0,0,0,1,0,0,0,0,1,0};
    const simd_double4x4 *m=&matrix_identity_double4x4;
    if ((uintptr_t)m%16 || memcmp(m,expected4,sizeof(expected4)) ||
        memcmp(&matrix_identity_double3x3,expected3,sizeof(expected3))) return 11;
    if (dlsym(RTLD_DEFAULT,"matrix_identity_double4x4")!=m) return 12;
    void *system=dlopen("/usr/lib/libSystem.B.dylib",RTLD_LAZY|RTLD_NOLOAD);
    if (!system || dlsym(system,"matrix_identity_double4x4")!=m) return 13;
    Dl_info info;
    if (!dladdr(m,&info) || !info.dli_fname || strcmp(info.dli_fname,argv[1])) return 14;
    unsigned checks=12;
    for (unsigned c=0;c<4;c++) for (unsigned row=0;row<4;row++) {
        if (m->columns[c][row]!=(double)(c==row)) return 15;
        checks++;
    }
    const double inputs[8][4]={{0,0,0,0},{1,2,3,1},{-2.5,4,5,-3},
        {1e-100,1e100,-1e-100,-1e100},{.5,-.25,.125,-.0625},
        {100,-200,300,-400},{-0.,1.,-1.,0.},{9,8,7,6}};
    for (unsigned i=0;i<8;i++) for (unsigned row=0;row<4;row++) {
        double value=0;
        for (unsigned c=0;c<4;c++) value+=m->columns[c][row]*inputs[i][c];
        if (value!=inputs[i][row]) return 16;
        checks++;
    }
    printf("SIMD_DOUBLE4_PROVIDER %s\n",info.dli_fname);
    printf("SIMD_DOUBLE4X4_ORIGINAL_BYTES_LAYOUT_REEXPORT_AND_USE_OK %u\n",checks);
    return 0;
}
