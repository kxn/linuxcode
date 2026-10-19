/* Version compatibility for native local code signing. No signing is faked.
 * Remote signing and new launch/library constraints are explicitly unsupported.
 */
#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
extern const CFStringRef kSecCodeSignerForceLibraryEntitlements;
extern const CFStringRef kSecCodeSignerLaunchConstraintParent;
extern const CFStringRef kSecCodeSignerLaunchConstraintResponsible;
extern const CFStringRef kSecCodeSignerLaunchConstraintSelf;
extern const CFStringRef kSecCodeSignerLibraryConstraint;
static OSStatus unavailable(CFErrorRef *error) {
    if(error)*error=CFErrorCreate(NULL,kCFErrorDomainOSStatus,errSecUnimplemented,NULL);
    return errSecUnimplemented;
}
OSStatus SecCodeSignerRemoteCreate(CFDictionaryRef params, CFArrayRef chain, uint32_t flags, CFTypeRef *signer, CFErrorRef *error) {
    fprintf(stderr,"REMOTE_SIGNING_UNIMPLEMENTED_CALLED create\n");
    if(!signer)return errSecParam;*signer=NULL;return unavailable(error);
}
OSStatus SecCodeSignerRemoteAddSignature(CFTypeRef signer, SecStaticCodeRef code, uint32_t flags, void *handler, CFErrorRef *error) {
    fprintf(stderr,"REMOTE_SIGNING_UNIMPLEMENTED_CALLED add-signature\n");
    return unavailable(error);
}
CFArrayRef SecTrustCopyCertificateChain(SecTrustRef trust) {
    if(!trust||CFGetTypeID(trust)!=SecTrustGetTypeID())return NULL;
    CFIndex count=SecTrustGetCertificateCount(trust);if(count<=0)return NULL;
    CFMutableArrayRef chain=CFArrayCreateMutable(NULL,count,&kCFTypeArrayCallBacks);if(!chain)return NULL;
    for(CFIndex i=0;i<count;i++){
        SecCertificateRef certificate=SecTrustGetCertificateAtIndex(trust,i);
        if(!certificate){CFRelease(chain);return NULL;}
        CFArrayAppendValue(chain,certificate);
    }
    return chain;
}
OSStatus SecCodeSignerCreate(CFDictionaryRef params, uint32_t flags, CFTypeRef *signer) {
    if(!signer)return errSecParam;*signer=NULL;
    if(params&&CFGetTypeID(params)!=CFDictionaryGetTypeID())return errSecParam;
    if(params){
        const CFStringRef unsupported[]={kSecCodeSignerLaunchConstraintParent,kSecCodeSignerLaunchConstraintResponsible,kSecCodeSignerLaunchConstraintSelf,kSecCodeSignerLibraryConstraint};
        for(unsigned i=0;i<4;i++)if(CFDictionaryContainsKey(params,unsupported[i]))return errSecUnimplemented;
        CFTypeRef force=CFDictionaryGetValue(params,kSecCodeSignerForceLibraryEntitlements);
        if(force&&!CFEqual(force,kCFBooleanFalse))return errSecUnimplemented;
    }
    void *backend=dlopen("/usr/lib/libDarlingLocalIdentitySecurityBackend.dylib",RTLD_NOW|RTLD_LOCAL);
    OSStatus (*create)(CFDictionaryRef,uint32_t,CFTypeRef*)=backend?dlsym(backend,"SecCodeSignerCreate"):NULL;
    if(!create)return errSecNotAvailable;
    OSStatus result=create(params,flags,signer);
    if(getenv("LINUXCODE_CODE_SIGNER_TRACE"))fprintf(stderr,"NATIVE_LOCAL_CODE_SIGNER_CREATE STATUS %d FLAGS %u\n",(int)result,flags);
    return result;
}
