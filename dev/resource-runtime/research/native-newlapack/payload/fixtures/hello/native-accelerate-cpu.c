#include <Accelerate/Accelerate.h>
#include <dlfcn.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <mach-o/dyld.h>
#include "../../runtime/native-accelerate-cpu/resolvers.h"

static void check_owner(const void *function,const char *expected,Dl_info *result) {
    Dl_info info;assert(dladdr(function,&info));
    assert(strstr(info.dli_fname,expected));
    if (result) *result=info;
}
#define LOAD(name,var) __typeof__(&name) var=(__typeof__(&name))dlsym(library,#name);assert(var)

int main(int argc,char **argv) {
    if (argc!=2) return 2;
    void *library=dlopen(argv[1],RTLD_LAZY|RTLD_LOCAL);
    if (!library) { fprintf(stderr,"%s\n",dlerror());return 3; }
    unsigned loadedAccelerate=0,loadedVecLib=0;
    for (uint32_t i=0;i<_dyld_image_count();++i) {
        const char *path=_dyld_get_image_name(i);
        if (path && strstr(path,"/runtime/native-framework-stage/Accelerate.framework/")) ++loadedAccelerate;
        if (path && strstr(path,"/runtime/native-framework-stage/vecLib.framework/")) ++loadedVecLib;
    }
    assert(loadedAccelerate==1 && loadedVecLib==1);
    LOAD(vDSP_vsadd,add);LOAD(vDSP_vsaddD,addDouble);
    Dl_info vdsp;check_owner((const void *)add,"/runtime/native-library-stage/libvDSP.dylib",&vdsp);
    check_owner((const void *)addDouble,"/runtime/native-library-stage/libvDSP.dylib",NULL);
    uintptr_t (*resolver)(void)=(uintptr_t (*)(void))((uintptr_t)vdsp.dli_fbase+ORIGINAL_VDSP_VSADD_RESOLVER_OFFSET);
    __typeof__(add) implementation=(__typeof__(add))resolver();assert(implementation);
    check_owner((const void *)implementation,"/runtime/native-library-stage/libvDSP.dylib",NULL);
    assert(add==implementation || (uintptr_t)add==(uintptr_t)vdsp.dli_fbase+ORIGINAL_VDSP_VSADD_STUB_OFFSET);
    const unsigned lengths[]={0,1,2,3,7,8,15,16,17,31,32,33,63,64,65,129,257};
    const int inputStrides[]={1,2,-1},outputStrides[]={1,3,-2};
    float input[1024],output[1024];unsigned char written[1024];float scalar=1.25f;unsigned cases=0;
    __typeof__(add) paths[]={add,implementation};
    for (unsigned path=0;path<2;++path)
      for (unsigned count=0;count<sizeof(lengths)/sizeof(lengths[0]);++count)
       for (unsigned ia=0;ia<3;++ia) for (unsigned ic=0;ic<3;++ic) {
        unsigned n=lengths[count];int a=inputStrides[ia],c=outputStrides[ic];
        for (unsigned i=0;i<1024;++i) { input[i]=((int)(i%17)-8)*0.5f;output[i]=98765;written[i]=0; }
        int firstA=a<0 && n ? (n-1)*(-a) : 0,firstC=c<0 && n ? (n-1)*(-c) : 0;
        paths[path](input+firstA,a,&scalar,output+firstC,c,n);
        for (unsigned i=0;i<n;++i) {
            int index=firstC+(int)i*c;written[index]=1;
            assert(output[index]==input[firstA+(int)i*a]+scalar);
        }
        for (unsigned i=0;i<1024;++i) if (!written[i]) assert(output[i]==98765);
        ++cases;
    }
    double sourceDouble[]={-1,0.5,0,7,128},resultDouble[5]={0},scalarDouble=2.25;
    addDouble(sourceDouble,1,&scalarDouble,resultDouble,1,5);
    for (unsigned i=0;i<5;++i) assert(resultDouble[i]==sourceDouble[i]+scalarDouble);
    printf("ORIGINAL_VDSP_RESOLVER_STRIDES_FLOAT_CASES_DOUBLE_OK %u\n",cases);

    LOAD(BNNSGraphCompileOptionsMakeDefault,make);LOAD(BNNSGraphCompileOptionsDestroy,destroy);
    LOAD(BNNSGraphCompileOptionsGetTargetSingleThread,getSingle);LOAD(BNNSGraphCompileOptionsSetTargetSingleThread,setSingle);
    LOAD(BNNSGraphCompileOptionsGetGenerateDebugInfo,getDebug);LOAD(BNNSGraphCompileOptionsSetGenerateDebugInfo,setDebug);
    check_owner((const void *)make,"/runtime/native-library-stage/libBNNS.dylib",NULL);
    bnns_graph_compile_options_t first=make(),second=make();
    assert(first.data && second.data && first.data!=second.data && first.size && second.size);
    assert(!getSingle(first) && !getSingle(second) && !getDebug(first) && !getDebug(second));
    setSingle(first,true);setDebug(first,true);
    assert(getSingle(first) && getDebug(first) && !getSingle(second) && !getDebug(second));
    setSingle(first,false);setDebug(first,false);assert(!getSingle(first) && !getDebug(first));
    destroy(first);destroy(second);
    puts("ORIGINAL_BNNS_GRAPH_COMPILE_OPTIONS_DEFAULTS_SET_GET_INDEPENDENCE_DESTROY_OK");

    LOAD(vImageConvert_Planar8toPlanarF,toFloat);LOAD(vImageConvert_PlanarFtoPlanar8,toByte);
    check_owner((const void *)toFloat,"/runtime/native-framework-stage/vImage.framework/",NULL);
    check_owner((const void *)toByte,"/runtime/native-framework-stage/vImage.framework/",NULL);
    unsigned char pixels[3][12],roundtrip[3][13];float floating[3][12];
    memset(pixels,0xa5,sizeof(pixels));memset(roundtrip,0xa5,sizeof(roundtrip));
    for (unsigned y=0;y<3;++y) for (unsigned x=0;x<12;++x) floating[y][x]=98765;
    for (unsigned y=0;y<3;++y) for (unsigned x=0;x<8;++x) pixels[y][x]=(y*73+x*19)&255;
    pixels[0][0]=0;pixels[0][1]=255;
    vImage_Buffer inputImage={pixels,3,8,sizeof(pixels[0])},floatImage={floating,3,8,sizeof(floating[0])},byteImage={roundtrip,3,8,sizeof(roundtrip[0])};
    assert(toFloat(&inputImage,&floatImage,255,0,kvImageNoFlags)==kvImageNoError);
    for (unsigned y=0;y<3;++y) for (unsigned x=0;x<8;++x)
        assert(fabsf(floating[y][x]-(float)pixels[y][x])<0.0001f);
    assert(toByte(&floatImage,&byteImage,255,0,kvImageNoFlags)==kvImageNoError);
    for (unsigned y=0;y<3;++y) for (unsigned x=0;x<8;++x) assert(roundtrip[y][x]==pixels[y][x]);
    puts("ORIGINAL_VIMAGE_PADDED_ROWS_BYTE_FLOAT_BYTE_NUMERIC_ROUNDTRIP_OK");
    return 0;
}
