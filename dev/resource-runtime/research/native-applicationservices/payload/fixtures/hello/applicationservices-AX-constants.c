#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int main(int argc,char **argv) {
    if (argc<3 || (argc-1)%2) return 10;
    void *h=dlopen("/System/Library/Frameworks/ApplicationServices.framework/Versions/A/ApplicationServices",RTLD_NOW);
    if (!h) { fprintf(stderr,"AX_DLOPEN_FAILED %s\n",dlerror()); return 11; }
    unsigned checked=0;
    for (int i=1;i<argc;i+=2) {
        const CFStringRef *cell=(const CFStringRef *)dlsym(h,argv[i]);
        if (!cell || !*cell || dlsym(RTLD_DEFAULT,argv[i])!=cell) return 12;
        char value[4096];
        if (!CFStringGetCString(*cell,value,sizeof(value),kCFStringEncodingUTF8) || strcmp(value,argv[i+1])) return 13;
        Dl_info info;
        if (!dladdr(cell,&info) || !info.dli_fname || !strstr(info.dli_fname,"/HIServices.framework/")) return 14;
        printf("AX_VALUE %s %s\n",argv[i],value);
        printf("AX_PROVIDER %s\n",info.dli_fname);
        checked++;
    }
    printf("APPLICATIONSERVICES_ORIGINAL_AX_CFSTRING_VALUES_OK %u\n",checked);
    return 0;
}
