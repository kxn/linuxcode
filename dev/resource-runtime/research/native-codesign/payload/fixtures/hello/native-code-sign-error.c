#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
extern const CFStringRef kSecCodeSignerIdentity;
extern OSStatus SecCodeSignerCreate(CFDictionaryRef,uint32_t,CFTypeRef*);
extern OSStatus SecCodeSignerAddSignatureWithErrors(CFTypeRef,SecStaticCodeRef,uint32_t,CFErrorRef*);
int main(int argc,char **argv) {
    setbuf(stdout,NULL);if(argc!=2)return 2;
    CFTypeRef signer=NULL;const void *keys[]={kSecCodeSignerIdentity},*values[]={kCFNull};
    CFDictionaryRef params=CFDictionaryCreate(NULL,keys,values,1,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    OSStatus status=SecCodeSignerCreate(params,128,&signer);printf("NATIVE_SIGNER_CREATE_STATUS %d\n",(int)status);if(status||!signer)return 3;
    void *add=(void*)SecCodeSignerAddSignatureWithErrors;Dl_info owner;dladdr(add,&owner);
    printf("NATIVE_SIGNER_ADD_ADDRESS %p OWNER %s\n",add,owner.dli_fname);
    puts("NATIVE_SIGNER_ERROR_CAPTURE_PAUSE");sleep(12);
    CFURLRef url=CFURLCreateFromFileSystemRepresentation(NULL,(const UInt8*)argv[1],strlen(argv[1]),true);SecStaticCodeRef code=NULL;
    status=SecStaticCodeCreateWithPath(url,0,&code);printf("NATIVE_STATIC_CODE_CREATE_STATUS %d\n",(int)status);if(status||!code)return 4;
    CFErrorRef error=NULL;status=SecCodeSignerAddSignatureWithErrors(signer,code,0,&error);printf("NATIVE_SIGN_ADD_STATUS %d\n",(int)status);
    if(error){CFShow(error);CFDictionaryRef info=CFErrorCopyUserInfo(error);if(info){CFShow(info);CFRelease(info);}CFRelease(error);}
    CFRelease(code);CFRelease(url);CFRelease(params);CFRelease(signer);return status?1:0;
}
