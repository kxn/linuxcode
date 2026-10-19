#include <CoreFoundation/CoreFoundation.h>
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc,char **argv) {
    setbuf(stdout,NULL);
    assert(!getenv("DISPLAY") && !getenv("WAYLAND_DISPLAY") && !getenv("XAUTHORITY"));
    assert(argc>1 && (argc-1)%3==0);
    for (int n=1;n<argc;n+=3) {
        void *library=dlopen(argv[n],RTLD_LAZY|RTLD_LOCAL);
        if (!library) {fprintf(stderr,"IDENTIFIER_LOAD_FAILED %s: %s\n",argv[n],dlerror());return 2;}
        const CFStringRef *slot=dlsym(library,argv[n+1]);
        Dl_info owner;
        assert(slot && dladdr(slot,&owner) && !strcmp(owner.dli_fname,argv[n]));
        CFStringRef value=*slot;
        assert(value && CFGetTypeID(value)==CFStringGetTypeID());
        CFStringRef expected=CFStringCreateWithCString(NULL,argv[n+2],kCFStringEncodingUTF8);
        assert(expected && CFEqual(value,expected));
        CFStringRef copy=CFStringCreateCopy(NULL,value);
        assert(copy && CFGetTypeID(copy)==CFStringGetTypeID() && CFEqual(copy,expected));
        CFMutableStringRef mutable=CFStringCreateMutableCopy(NULL,0,value);
        assert(mutable);
        CFStringAppend(mutable,CFSTR("!"));
        assert(CFStringGetLength(mutable)==CFStringGetLength(expected)+1);
        assert(!CFEqual(mutable,value) && CFEqual(value,expected) && CFEqual(copy,expected));
        CFRelease(mutable);CFRelease(copy);CFRelease(expected);
        printf("ORIGINAL_RESOURCE_IDENTIFIER_OK %s %s\n",argv[n+1],argv[n+2]);
        dlclose(library);
    }
    printf("ORIGINAL_RESOURCE_IDENTIFIERS_NATIVE_OK %d\n",(argc-1)/3);
    return 0;
}
