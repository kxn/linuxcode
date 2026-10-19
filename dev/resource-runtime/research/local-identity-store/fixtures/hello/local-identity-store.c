#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do { if(!(x)){fprintf(stderr,"CHECK_FAILED line %d\n",__LINE__);return 1;}checks++; } while(0)
int main(int argc,char **argv){
    setbuf(stdout,NULL);CHECK(argc==9);Dl_info owner;CHECK(dladdr((void*)SecItemCopyMatching,&owner));CHECK(strstr(owner.dli_fname,"local-identity-store-readonly-v2/frameworks/"));
    CFMutableDictionaryRef q=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(q,kSecClass,kSecClassIdentity);CFDictionarySetValue(q,kSecReturnRef,kCFBooleanTrue);CFDictionarySetValue(q,kSecMatchLimit,kSecMatchLimitAll);
    CFTypeRef result=NULL;
    const OSStatus errors[]={errSecItemNotFound,errSecInteractionNotAllowed,errSecDecode,errSecNotAvailable,errSecDecode,errSecNotAvailable};
    for(int i=0;i<6;i++){setenv("LINUXCODE_IDENTITY_STORE",argv[i+2],1);result=(CFTypeRef)1;OSStatus s=SecItemCopyMatching(q,&result);printf("LOCAL_IDENTITY_NEGATIVE %d STATUS %d\n",i,(int)s);CHECK(s==errors[i]);CHECK(result==NULL);}
    setenv("LINUXCODE_IDENTITY_STORE",argv[1],1);CHECK(SecItemCopyMatching(q,&result)==0);CHECK(result&&CFGetTypeID(result)==CFArrayGetTypeID());CHECK(CFArrayGetCount(result)==1);
    SecIdentityRef ident=(SecIdentityRef)CFArrayGetValueAtIndex(result,0);CHECK(CFGetTypeID(ident)==SecIdentityGetTypeID());SecCertificateRef cert=NULL;SecKeyRef key=NULL;
    CHECK(SecIdentityCopyCertificate(ident,&cert)==0&&cert);CHECK(SecIdentityCopyPrivateKey(ident,&key)==0&&key);
    SecKeyRef pub=SecCertificateCopyKey(cert);CHECK(pub);CFDataRef message=CFDataCreate(NULL,(const UInt8*)"native identity-store signing",29);
    CFDataRef signature=SecKeyCreateSignature(key,kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256,message,NULL);CHECK(signature);CHECK(SecKeyVerifySignature(pub,kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256,message,signature,NULL));
    CFRelease(signature);CFRelease(message);CFRelease(pub);CFRelease(key);CFRelease(cert);CFRelease(result);result=NULL;
    CFDictionarySetValue(q,kSecMatchLimit,kSecMatchLimitOne);CHECK(SecItemCopyMatching(q,&result)==0);CHECK(CFGetTypeID(result)==SecIdentityGetTypeID());CFRelease(result);
    CFDictionarySetValue(q,kSecAttrLabel,CFSTR("missing"));CHECK(SecItemCopyMatching(q,&result)==errSecItemNotFound&&result==NULL);CFDictionaryRemoveValue(q,kSecAttrLabel);
    CFDictionarySetValue(q,kSecClass,kSecClassCertificate);CFDictionarySetValue(q,kSecReturnData,kCFBooleanTrue);CFDictionarySetValue(q,kSecReturnAttributes,kCFBooleanTrue);
    CHECK(SecItemCopyMatching(q,&result)==0);CHECK(CFGetTypeID(result)==CFDictionaryGetTypeID());CHECK(CFGetTypeID(CFDictionaryGetValue(result,kSecValueRef))==SecCertificateGetTypeID());CHECK(CFGetTypeID(CFDictionaryGetValue(result,kSecValueData))==CFDataGetTypeID());CHECK(CFEqual(CFDictionaryGetValue(result,kSecAttrLabel),CFSTR("fixture")));CFRelease(result);
    CFDictionarySetValue(q,CFSTR("unsupportedQuery"),kCFBooleanTrue);CHECK(SecItemCopyMatching(q,&result)==errSecParam&&result==NULL);CFDictionaryRemoveValue(q,CFSTR("unsupportedQuery"));
    setenv("LINUXCODE_IDENTITY_STORE",argv[8],1);CHECK(SecItemCopyMatching(q,&result)==errSecDecode&&result==NULL);
    CFRelease(q);printf("LOCAL_IDENTITY_STORE_NATIVE_OBJECTS_SIGNATURE_QUERY_SHAPES_AND_FAILURES_OK %u\n",checks);return 0;
}
