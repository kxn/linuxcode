#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <stdlib.h>
extern CFArrayRef SecItemCopyParentCertificates_osx(SecCertificateRef,void *);
static unsigned checks;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"POLICY_CHECK_FAILED %d\n",__LINE__);return 1;}checks++;}while(0)
int main(int argc,char **argv){
    setbuf(stdout,NULL);CHECK(argc==3);
    setenv("LINUXCODE_IDENTITY_STORE",argv[1],1);
    SecIdentityRef preference=(SecIdentityRef)1;
    CHECK(SecIdentityCopyPreference(CFSTR("fixture"),0,NULL,&preference)==errSecItemNotFound);
    CHECK(preference==NULL);
    CHECK(SecIdentityCopyPreference(CFSTR("fixture"),0,NULL,NULL)==errSecParam);
    CHECK(SecItemCopyParentCertificates_osx(NULL,NULL)==NULL);
    CFMutableDictionaryRef q=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(q,kSecClass,kSecClassIdentity);CFDictionarySetValue(q,kSecReturnRef,kCFBooleanTrue);
    CFDictionarySetValue(q,kSecMatchLimit,kSecMatchLimitAll);CFDictionarySetValue(q,kSecAttrCanSign,kCFBooleanTrue);
    SecPolicyRef code=SecPolicyCreateWithProperties(kSecPolicyAppleCodeSigning,NULL);
    CHECK(code);CFDictionarySetValue(q,kSecMatchPolicy,code);CFTypeRef result=NULL;
    CHECK(SecItemCopyMatching(q,&result)==0);CHECK(result&&CFGetTypeID(result)==CFArrayGetTypeID());
    CHECK(CFArrayGetCount(result)==1);
    SecIdentityRef ident=(SecIdentityRef)CFArrayGetValueAtIndex(result,0);SecKeyRef key=NULL;
    CHECK(CFGetTypeID(ident)==SecIdentityGetTypeID());CHECK(SecIdentityCopyPrivateKey(ident,&key)==0&&key);
    SecCertificateRef certificate=NULL;CHECK(SecIdentityCopyCertificate(ident,&certificate)==0&&certificate);
    CFArrayRef parents=SecItemCopyParentCertificates_osx(certificate,NULL);
    CHECK(parents&&CFArrayGetCount(parents)==1);
    CHECK(CFEqual(CFArrayGetValueAtIndex(parents,0),certificate));CFRelease(parents);
    SecIdentityRef resolved=(SecIdentityRef)1;
    CHECK(SecIdentityCreateWithCertificate(NULL,NULL,&resolved)==errSecParam&&resolved==NULL);
    CHECK(SecIdentityCreateWithCertificate(NULL,certificate,NULL)==errSecParam);
    CHECK(SecIdentityCreateWithCertificate(NULL,certificate,&resolved)==0&&resolved);
    SecCertificateRef resolvedCert=NULL;SecKeyRef resolvedKey=NULL;
    CHECK(SecIdentityCopyCertificate(resolved,&resolvedCert)==0&&CFEqual(resolvedCert,certificate));
    CHECK(SecIdentityCopyPrivateKey(resolved,&resolvedKey)==0&&resolvedKey);
    CFDataRef resolvedBytes=SecKeyCopyExternalRepresentation(resolvedKey,NULL),keyBytes=SecKeyCopyExternalRepresentation(key,NULL);
    CHECK(resolvedBytes&&keyBytes&&CFEqual(resolvedBytes,keyBytes));
    CFRelease(resolvedBytes);CFRelease(keyBytes);CFRelease(resolvedKey);CFRelease(resolvedCert);CFRelease(resolved);
    CFRelease(certificate);
    CFDataRef msg=CFDataCreate(NULL,(const UInt8*)"policy-selected signer",22);
    CFDataRef sig=SecKeyCreateSignature(key,kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256,msg,NULL);CHECK(sig);
    SecKeyRef pub=SecKeyCopyPublicKey(key);CHECK(pub);
    CHECK(SecKeyVerifySignature(pub,kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256,msg,sig,NULL));
    CFRelease(pub);CFRelease(sig);CFRelease(msg);CFRelease(key);CFRelease(result);result=NULL;
    const char *rejected[]={"wrong-eku","wrong-ku","unknown-critical","expired"};
    for(unsigned i=0;i<4;i++){
        CFStringRef label=CFStringCreateWithCString(NULL,rejected[i],kCFStringEncodingUTF8);
        CFDictionarySetValue(q,kSecAttrLabel,label);CFRelease(label);
        CHECK(SecItemCopyMatching(q,&result)==errSecItemNotFound&&result==NULL);
    }
    CFDictionaryRemoveValue(q,kSecAttrLabel);
    CFDictionarySetValue(q,kSecAttrCanSign,kCFBooleanFalse);
    CHECK(SecItemCopyMatching(q,&result)==errSecItemNotFound&&result==NULL);
    CFDictionarySetValue(q,kSecAttrCanSign,kCFBooleanTrue);
    SecPolicyRef ssl=SecPolicyCreateSSL(true,NULL);CHECK(ssl);CFDictionarySetValue(q,kSecMatchPolicy,ssl);
    CHECK(SecItemCopyMatching(q,&result)==errSecParam&&result==NULL);
    CFDictionarySetValue(q,kSecMatchPolicy,CFSTR("invalid"));
    CHECK(SecItemCopyMatching(q,&result)==errSecParam&&result==NULL);
    CFDictionarySetValue(q,kSecMatchPolicy,code);setenv("LINUXCODE_IDENTITY_STORE",argv[2],1);
    CHECK(SecItemCopyMatching(q,&result)==errSecInteractionNotAllowed&&result==NULL);
    CFDataRef lockedCertData=NULL;SecCertificateRef lockedCertificate=NULL;
    CFURLRef storeURL=CFURLCreateFromFileSystemRepresentation(NULL,(const UInt8*)argv[1],strlen(argv[1]),false);
    CFReadStreamRef stream=CFReadStreamCreateWithFile(NULL,storeURL);CHECK(stream&&CFReadStreamOpen(stream));
    CFPropertyListRef store=CFPropertyListCreateWithStream(NULL,stream,0,kCFPropertyListImmutable,NULL,NULL);
    CHECK(store);CFReadStreamClose(stream);CFRelease(stream);CFRelease(storeURL);
    CFArrayRef items=CFDictionaryGetValue(store,CFSTR("items"));lockedCertData=CFDictionaryGetValue(CFArrayGetValueAtIndex(items,0),CFSTR("certificate"));
    lockedCertificate=SecCertificateCreateWithData(NULL,lockedCertData);CHECK(lockedCertificate);
    resolved=(SecIdentityRef)1;CHECK(SecIdentityCreateWithCertificate(NULL,lockedCertificate,&resolved)==errSecInteractionNotAllowed&&resolved==NULL);
    CFRelease(lockedCertificate);CFRelease(store);
    preference=(SecIdentityRef)1;
    CHECK(SecIdentityCopyPreference(CFSTR("fixture"),0,NULL,&preference)==errSecInteractionNotAllowed&&preference==NULL);
    CFRelease(ssl);CFRelease(code);CFRelease(q);
    printf("LOCAL_IDENTITY_LEAF_POLICY_OK %u\n",checks);return 0;
}
