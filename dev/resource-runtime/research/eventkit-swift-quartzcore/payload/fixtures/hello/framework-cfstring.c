#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int main(int argc,char** argv) {
    if(argc!=5 && argc!=6) return 10;
    int binding=RTLD_NOW;
    if(argc==6) {
        if(!strcmp(argv[5],"lazy")) binding=RTLD_LAZY;
        else if(strcmp(argv[5],"now")) return 10;
    }
    void* framework=dlopen(argv[1],binding|RTLD_GLOBAL);
    if(!framework) { fprintf(stderr,"CFSTRING_DLOPEN_FAILED %s\n",dlerror()); return 11; }
    const CFStringRef* cell=(const CFStringRef*)dlsym(framework,argv[2]);
    if(!cell || !*cell) { puts("CFSTRING_MISSING_SYMBOL"); return 12; }
    if(dlsym(RTLD_DEFAULT,argv[2])!=cell) return 13;
    CFTypeID type=CFGetTypeID(*cell);
    if(!type || type!=CFStringGetTypeID()) return 14;
    char text[1024];
    if(!CFStringGetCString(*cell,text,sizeof(text),kCFStringEncodingUTF8) || strcmp(text,argv[3])) return 15;
    Dl_info owner;
    if(!dladdr(cell,&owner) || !owner.dli_fname || !strstr(owner.dli_fname,argv[4])) return 16;
    printf("CFSTRING_VALUE %s %s\n",argv[2],text);
    printf("CFSTRING_TYPE_ID %lu\n",(unsigned long)type);
    printf("CFSTRING_PROVIDER %s\n",owner.dli_fname);
    puts("ORIGINAL_CFSTRING_TYPE_UTF8_VALUE_PROVIDER_AND_GLOBAL_IDENTITY_OK");
    return 0;
}
