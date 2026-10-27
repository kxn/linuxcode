#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>
#include <stdio.h>
#include <stdlib.h>
extern CFArrayRef SecItemCopyParentCertificates_osx(SecCertificateRef,void*);
static unsigned checks;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"CHAIN_CHECK_FAILED line=%d\n",__LINE__);return 1;}checks++;}while(0)
static CFDataRef data_at(const char *path){
    FILE *f=fopen(path,"rb");if(!f)return NULL;fseek(f,0,SEEK_END);long size=ftell(f);rewind(f);
    if(size<=0){fclose(f);return NULL;}UInt8 *bytes=malloc(size);if(!bytes){fclose(f);return NULL;}
    size_t n=fread(bytes,1,size,f);fclose(f);CFDataRef data=n==size?CFDataCreate(NULL,bytes,size):NULL;free(bytes);return data;
}
int main(int argc,char **argv){
    setbuf(stdout,NULL);CHECK(argc==4);setenv("LINUXCODE_IDENTITY_STORE",argv[1],1);
    CFDataRef bytes=data_at(argv[1]);CHECK(bytes);
    CFDictionaryRef store=(CFDictionaryRef)CFPropertyListCreateWithData(NULL,bytes,kCFPropertyListImmutable,NULL,NULL);CHECK(store);CFRelease(bytes);
    CFArrayRef items=CFDictionaryGetValue(store,CFSTR("items")),extras=CFDictionaryGetValue(store,CFSTR("certificates"));CHECK(CFArrayGetCount(items)==1&&CFArrayGetCount(extras)==2);
    CFDataRef leafDER=CFDictionaryGetValue(CFArrayGetValueAtIndex(items,0),CFSTR("certificate"));
    SecCertificateRef leaf=SecCertificateCreateWithData(NULL,leafDER);CHECK(leaf);
    CFMutableDictionaryRef query=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(query,kSecClass,kSecClassIdentity);CFDictionarySetValue(query,kSecReturnRef,kCFBooleanTrue);CFDictionarySetValue(query,kSecMatchLimit,kSecMatchLimitAll);
    CFTypeRef result=NULL;CHECK(SecItemCopyMatching(query,&result)==0);CHECK(CFArrayGetCount(result)==1);CFRelease(result);result=NULL;
    SecIdentityRef identity=NULL;CHECK(SecIdentityCreateWithCertificate(NULL,leaf,&identity)==0&&identity);
    SecKeyRef key=NULL;CHECK(SecIdentityCopyPrivateKey(identity,&key)==0&&key);
    CFDataRef message=CFDataCreate(NULL,(const UInt8*)"imported P12 native signing",26);
    CFDataRef signature=SecKeyCreateSignature(key,kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256,message,NULL);CHECK(signature);
    SecKeyRef public=SecCertificateCopyKey(leaf);CHECK(public);CHECK(SecKeyVerifySignature(public,kSecKeyAlgorithmRSASignatureMessagePKCS1v15SHA256,message,signature,NULL));
    CFRelease(signature);CFRelease(message);CFRelease(public);CFRelease(key);CFRelease(identity);
    CFDictionarySetValue(query,kSecClass,kSecClassCertificate);CHECK(SecItemCopyMatching(query,&result)==0);CHECK(CFArrayGetCount(result)==3);CFRelease(result);result=NULL;
    SecPolicyRef code=SecPolicyCreateWithProperties(kSecPolicyAppleCodeSigning,NULL);CHECK(code);CFDictionarySetValue(query,kSecMatchPolicy,code);
    CHECK(SecItemCopyMatching(query,&result)==0);CHECK(CFArrayGetCount(result)==1);CFRelease(result);result=NULL;CFRelease(code);CFDictionaryRemoveValue(query,kSecMatchPolicy);
    CFArrayRef parents=SecItemCopyParentCertificates_osx(leaf,NULL);CHECK(parents&&CFArrayGetCount(parents)==1);
    SecCertificateRef intermediate=(SecCertificateRef)CFRetain(CFArrayGetValueAtIndex(parents,0));CFRelease(parents);
    parents=SecItemCopyParentCertificates_osx(intermediate,NULL);CHECK(parents&&CFArrayGetCount(parents)==1);
    SecCertificateRef root=(SecCertificateRef)CFRetain(CFArrayGetValueAtIndex(parents,0));CFRelease(parents);
    CFDictionarySetValue(query,kSecMatchPolicy,SecPolicyCreateBasicX509());CHECK(SecItemCopyMatching(query,&result)==0);CHECK(CFArrayGetCount(result)==3);CFRelease(result);result=NULL;
    CFArrayRef certificates=CFArrayCreate(NULL,(const void*[]){leaf,intermediate},2,&kCFTypeArrayCallBacks);
    SecPolicyRef basic=SecPolicyCreateBasicX509();SecTrustRef trust=NULL;CHECK(SecTrustCreateWithCertificates(certificates,basic,&trust)==0);
    CFArrayRef anchors=CFArrayCreate(NULL,(const void*[]){root},1,&kCFTypeArrayCallBacks);
    CHECK(SecTrustSetAnchorCertificates(trust,anchors)==0);CHECK(SecTrustSetAnchorCertificatesOnly(trust,true)==0);
    SecTrustResultType verdict=kSecTrustResultInvalid;OSStatus status=SecTrustEvaluate(trust,&verdict);
    printf("NATIVE_CHAIN_EXPLICIT_ANCHOR status=%d result=%u\n",(int)status,(unsigned)verdict);
    CHECK(status==0&&(verdict==kSecTrustResultUnspecified||verdict==kSecTrustResultProceed));CFRelease(trust);CFRelease(anchors);
    bytes=data_at(argv[3]);CHECK(bytes);SecCertificateRef wrong=SecCertificateCreateWithData(NULL,bytes);CHECK(wrong);CFRelease(bytes);
    CHECK(SecTrustCreateWithCertificates(certificates,basic,&trust)==0);anchors=CFArrayCreate(NULL,(const void*[]){wrong},1,&kCFTypeArrayCallBacks);
    CHECK(SecTrustSetAnchorCertificates(trust,anchors)==0);CHECK(SecTrustSetAnchorCertificatesOnly(trust,true)==0);
    verdict=kSecTrustResultInvalid;status=SecTrustEvaluate(trust,&verdict);printf("NATIVE_CHAIN_WRONG_ANCHOR status=%d result=%u\n",(int)status,(unsigned)verdict);
    CHECK(status!=0||(verdict!=kSecTrustResultUnspecified&&verdict!=kSecTrustResultProceed));
    CFRelease(anchors);CFRelease(wrong);CFRelease(trust);CFRelease(basic);CFRelease(certificates);
    setenv("LINUXCODE_IDENTITY_STORE",argv[2],1);CHECK(SecItemCopyMatching(query,&result)==errSecDecode&&result==NULL);
    CFRelease(root);CFRelease(intermediate);CFRelease(leaf);CFRelease(query);CFRelease(store);
    printf("LOCAL_IDENTITY_CHAIN_OK %u\n",checks);return 0;
}
