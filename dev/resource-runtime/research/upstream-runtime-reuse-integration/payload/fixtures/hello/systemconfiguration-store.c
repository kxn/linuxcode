#include <SystemConfiguration/SystemConfiguration.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <dlfcn.h>
static unsigned checks,notifications;
static CFStringRef expected_key;
#define CHECK(c) do{checks++;if(!(c)){fprintf(stderr,"SC_STORE_FAIL line=%d %s error=%d %s\n",__LINE__,#c,SCError(),SCErrorString(SCError()));exit(1);}}while(0)
static void changed(SCDynamicStoreRef store,CFArrayRef keys,void* context) {
    (void)store;(void)context;
    for(CFIndex i=0;i<CFArrayGetCount(keys);i++)if(CFEqual(CFArrayGetValueAtIndex(keys,i),expected_key))notifications++;
}
int main(void) {
    setbuf(stdout,NULL);Dl_info owner={0};CHECK(dladdr((void*)SCDynamicStoreCreate,&owner));printf("SC_STORE_OWNER %s\n",owner.dli_fname);
    SCDynamicStoreContext context={0};SCDynamicStoreRef store=SCDynamicStoreCreate(NULL,CFSTR("org.darling.linuxcode.store-test"),changed,&context);CHECK(store);
    CHECK(CFGetTypeID(store)==SCDynamicStoreGetTypeID());
    expected_key=CFStringCreateWithFormat(NULL,NULL,CFSTR("State:/org.darling.linuxcode/test/%d"),getpid());CHECK(expected_key);
    CFArrayRef keys=CFArrayCreate(NULL,(const void**)&expected_key,1,&kCFTypeArrayCallBacks);CHECK(keys);
    CHECK(SCDynamicStoreSetNotificationKeys(store,keys,NULL));
    CFRunLoopSourceRef source=SCDynamicStoreCreateRunLoopSource(NULL,store,0);CHECK(source);
    CFRunLoopAddSource(CFRunLoopGetCurrent(),source,kCFRunLoopDefaultMode);
    CFStringRef value=CFSTR("real Linux native configd IPC");CHECK(SCDynamicStoreSetValue(store,expected_key,value));
    CFPropertyListRef copy=SCDynamicStoreCopyValue(store,expected_key);CHECK(copy && CFEqual(copy,value));CFRelease(copy);
    for(unsigned i=0;i<12 && !notifications;i++)CFRunLoopRunInMode(kCFRunLoopDefaultMode,.25,false);
    CHECK(notifications>0);
    int integer=197;CFNumberRef number=CFNumberCreate(NULL,kCFNumberIntType,&integer);CHECK(number);
    CHECK(SCDynamicStoreSetValue(store,expected_key,number));copy=SCDynamicStoreCopyValue(store,expected_key);
    int observed=0;CHECK(copy && CFGetTypeID(copy)==CFNumberGetTypeID());CHECK(CFNumberGetValue(copy,kCFNumberIntType,&observed) && observed==integer);CFRelease(copy);CFRelease(number);
    CHECK(SCDynamicStoreRemoveValue(store,expected_key));copy=SCDynamicStoreCopyValue(store,expected_key);CHECK(copy==NULL && SCError()==kSCStatusNoKey);
    CFRunLoopRemoveSource(CFRunLoopGetCurrent(),source,kCFRunLoopDefaultMode);CFRunLoopSourceInvalidate(source);
    CFRelease(source);CFRelease(keys);CFRelease(expected_key);CFRelease(store);
    printf("NATIVE_SYSTEMCONFIGURATION_REAL_CONFIGD_STORE_AND_NOTIFICATION_OK checks=%u notifications=%u\n",checks,notifications);return 0;
}
