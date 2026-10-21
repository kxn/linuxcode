#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <objc/message.h>
#include <objc/runtime.h>
typedef void (*Add)(const char*,unsigned);
typedef char* (*Metadata)(const char*);
static const char* description(id object) {
    id text=((id(*)(id,SEL))objc_msgSend)(object,sel_registerName("description"));
    const char* s=((const char*(*)(id,SEL))objc_msgSend)(text,sel_registerName("UTF8String"));
    return s?s:"NULL";
}
int main(int argc,char** argv) {
    assert(argc==3);
    Add add=(Add)dlsym(RTLD_DEFAULT,"xpc_add_bundle");
    Metadata version=(Metadata)dlsym(RTLD_DEFAULT,"launch_version_for_user_service_4coresim");
    Metadata path=(Metadata)dlsym(RTLD_DEFAULT,"launch_path_for_user_service_4coresim");
    assert(add && version && path);
    errno=0;add(argv[1],0);printf("CORE_SIMULATOR_ADD errno=%d\n",errno);fflush(stdout);
    char* v=version("com.apple.CoreSimulator.CoreSimulatorService");int ve=errno;
    char* p=path("com.apple.CoreSimulator.CoreSimulatorService");
    printf("CORE_SIMULATOR_REGISTERED version=%s errno=%d path=%s path_errno=%d\n",v?v:"NULL",ve,p?p:"NULL",errno);fflush(stdout);free(v);free(p);
    void* image=dlopen(argv[2],RTLD_LAZY|RTLD_LOCAL);
    if(!image)fprintf(stderr,"CoreSimulator dlopen: %s\n",dlerror());assert(image);
    Class cls=objc_getClass("SimServiceContext");assert(cls);
    id dir=((id(*)(id,SEL,const char*))objc_msgSend)((id)objc_getClass("NSString"),sel_registerName("stringWithUTF8String:"),"/Applications/Xcode.app/Contents/Developer");
    id error=NULL;id context=((id(*)(id,SEL,id,id*))objc_msgSend)((id)cls,sel_registerName("sharedServiceContextForDeveloperDir:error:"),dir,&error);
    printf("CORE_SIMULATOR_CONTEXT present=%d error=%s\n",context!=NULL,description(error));fflush(stdout);
    return context?0:1;
}
