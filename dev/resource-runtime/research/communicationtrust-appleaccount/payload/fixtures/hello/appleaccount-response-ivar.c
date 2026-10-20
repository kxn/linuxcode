#include <objc/runtime.h>
#include <objc/message.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static id send0(id object, const char *name) {
    return ((id (*)(id,SEL))objc_msgSend)(object,sel_registerName(name));
}
int main(int argc,char **argv) {
    if (argc!=4) return 10;
    void *library=dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL);
    if (!library) { fprintf(stderr,"AARESPONSE_LOAD_FAILED %s\n",dlerror()); return 11; }
    const uint32_t *cell=dlsym(library,"OBJC_IVAR_$_AAResponse._error");
    if (!cell) { puts("AARESPONSE_IVAR_MISSING"); return 12; }
    Class cls=objc_getClass("AAResponse");
    if (!cls || cls!=(Class)dlsym(library,"OBJC_CLASS_$_AAResponse")) return 13;
    Ivar ivar=class_getInstanceVariable(cls,"_error");
    if (!ivar || !ivar_getTypeEncoding(ivar) || ivar_getTypeEncoding(ivar)[0]!='@') return 14;
    ptrdiff_t offset=ivar_getOffset(ivar);
    if (offset!=*cell || offset!=strtol(argv[3],NULL,10)) return 15;
    if (offset<(ptrdiff_t)class_getInstanceSize(class_getSuperclass(cls)) ||
        offset+sizeof(id)>class_getInstanceSize(cls)) return 16;
    Dl_info owner;
    if (!dladdr(cell,&owner) || !owner.dli_fname || !strstr(owner.dli_fname,argv[2])) return 17;
    SEL getter=sel_registerName("error"); Method method=class_getInstanceMethod(cls,getter);
    Dl_info implementation;
    if (!method || !dladdr(method_getImplementation(method),&implementation) ||
        !implementation.dli_fname || !strstr(implementation.dli_fname,argv[2])) return 18;
    id pool=send0((id)objc_getClass("NSAutoreleasePool"),"new");
    id domain=((id (*)(id,SEL,const char *))objc_msgSend)((id)objc_getClass("NSString"),
        sel_registerName("stringWithUTF8String:"),"LinuxCodeIvarProbe");
    id error=((id (*)(id,SEL,id,long,id))objc_msgSend)((id)objc_getClass("NSError"),
        sel_registerName("errorWithDomain:code:userInfo:"),domain,73,NULL);
    if (!pool || !domain || !error) return 20;
    id reply=class_createInstance(cls,0); if (!reply) return 21;
    object_setIvar(reply,ivar,error);
    if (object_getIvar(reply,ivar)!=error || *(id *)((char *)reply+offset)!=error) return 22;
    id observed=((id (*)(id,SEL))objc_msgSend)(reply,getter);
    if (observed!=error || ((long (*)(id,SEL))objc_msgSend)(observed,sel_registerName("code"))!=73) return 23;
    object_setIvar(reply,ivar,NULL); object_dispose(reply); send0(pool,"drain");
    printf("AARESPONSE_IVAR_OFFSET %td\n",offset);
    printf("AARESPONSE_PROVIDER %s\n",owner.dli_fname);
    puts("ORIGINAL_AARESPONSE_IVAR_LAYOUT_NSError_AND_GETTER_OK");
    return 0;
}
