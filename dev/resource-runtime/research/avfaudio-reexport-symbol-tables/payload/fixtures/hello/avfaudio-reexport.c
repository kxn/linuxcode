#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

#define CHECK(v) do { if (!(v)) { fprintf(stderr,"AVF_REEXPORT_FAIL %d %s\n",__LINE__,#v); return 1; } } while(0)
int main(int argc,char** argv) {
    setbuf(stdout,NULL);
    CHECK(argc==5);
    void* avf=dlopen(argv[2],RTLD_LAZY|RTLD_LOCAL|RTLD_FIRST);
    if (!avf) { fprintf(stderr,"AVF_DLOPEN_FAILED %s\n",dlerror()); return 10; }
    const char* symbol="AVAudioSessionRoutingContextChangeNotification";
    const CFStringRef* slot=dlsym(avf,symbol);
    if (!strcmp(argv[1],"missing")) {
        CHECK(slot==NULL);
        puts("AVF_OLD_PROVIDER_REEXPORT_ABSENT_OK");
        return 0;
    }
    CHECK(!strcmp(argv[1],"present"));
    CHECK(slot && *slot);
    void* session=dlopen(argv[3],RTLD_LAZY|RTLD_LOCAL|RTLD_FIRST);
    if (!session) { fprintf(stderr,"AUDIOSESSION_DLOPEN_FAILED %s\n",dlerror()); return 10; }
    const CFStringRef* direct=dlsym(session,symbol);
    CHECK(direct==slot && *direct==*slot);
    Dl_info owner;
    CHECK(dladdr(slot,&owner) && owner.dli_fname);
    printf("AVF_REEXPORT_TERMINAL_OWNER %s\n",owner.dli_fname);
    CHECK(CFGetTypeID(*slot)==CFStringGetTypeID());
    CHECK(CFStringGetLength(*slot)==(CFIndex)strlen(argv[4]));
    char text[4096];
    CHECK(CFStringGetCString(*slot,text,sizeof(text),kCFStringEncodingUTF8));
    CHECK(!strcmp(text,argv[4]));
    printf("AVF_ORIGINAL_REEXPORT_SLOT_OBJECT_IDENTITY_AND_CFSTRING_VALUE_OK value=%s\n",text);
    return 0;
}
