#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned checks;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"POLICY_CHECK_FAILED %d\n",__LINE__);return 1;}checks++;}while(0)
int main(int argc,char **argv){
    setbuf(stdout,NULL);CHECK(argc==3);
    setenv("LINUXCODE_IDENTITY_STORE",argv[1],1);
    SecIdentityRef preference=(SecIdentityRef)1;
    CHECK(SecIdentityCopyPreference(CFSTR("fixture"),0,NULL,&preference)==errSecItemNotFound);
    CHECK(preference==NULL);
    CHECK(SecIdentityCopyPreference(CFSTR("fixture"),0,NULL,NULL)==errSecParam);
    CFMutableDictionaryRef q=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(q,kSecClass,kSecClassIdentity);CFDictionarySetValue(q,kSecReturnRef,kCFBooleanTrue);
    CFDictionarySetValue(q,kSecMatchLimit,kSecMatchLimitAll);CFDictionarySetValue(q,kSecAttrCanSign,kCFBooleanTrue);
    SecPolicyRef code=SecPolicyCreateWithProperties(kSecPolicyAppleCodeSigning,NULL);
    CHECK(code);CFDictionarySetValue(q,kSecMatchPolicy,code);CFTypeRef result=NULL;
    CHECK(SecItemCopyMatching(q,&result)==0);CHECK(result&&CFGetTypeID(result)==CFArrayGetTypeID());
    CHECK(CFArrayGetCount(result)==1);
    SecIdentityRef ident=(SecIdentityRef)CFArrayGetValueAtIndex(result,0);SecKeyRef key=NULL;
    CHECK(CFGetTypeID(ident)==SecIdentityGetTypeID());CHECK(SecIdentityCopyPrivateKey(ident,&key)==0&&key);
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
    preference=(SecIdentityRef)1;
    CHECK(SecIdentityCopyPreference(CFSTR("fixture"),0,NULL,&preference)==errSecInteractionNotAllowed&&preference==NULL);
    CFRelease(ssl);CFRelease(code);CFRelease(q);
    printf("LOCAL_IDENTITY_LEAF_POLICY_OK %u\n",checks);return 0;
}
