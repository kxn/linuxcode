#include <dlfcn.h>
#include <stdio.h>
int main(int argc,char **argv) {
    fputs("NATIVE_FOUNDATION_PROBE_MAIN_ENTERED\n",stderr);
    if (argc!=2)return 2;
    void *image=dlopen(argv[1],RTLD_LAZY|RTLD_LOCAL);
    if (!image) { fprintf(stderr,"NATIVE_FOUNDATION_DLOPEN_FAILED: %s\n",dlerror());return 1; }
    fputs("NATIVE_FOUNDATION_DLOPEN_COMPLETED\n",stderr);
    return 0;
}
