#include <Security/Security.h>
#include <Security/CMSEncoder.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdio.h>
#include <stdlib.h>
static OSStatus report(const char *name,OSStatus status){printf("CERTIFICATE_PREFLIGHT %s %d\n",name,(int)status);return status;}
int main(int argc,char **argv){
    setbuf(stdout,NULL);if(argc!=2)return 2;
    const void *keys[]={kSecClass,kSecReturnRef,kSecMatchLimit,kSecAttrLabel};
    const void *values[]={kSecClassIdentity,kCFBooleanTrue,kSecMatchLimitOne,CFSTR("fixture")};
    CFDictionaryRef query=CFDictionaryCreate(NULL,keys,values,4,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    CFTypeRef ident=NULL;if(report("identity",SecItemCopyMatching(query,&ident)))return 1;
    SecCertificateRef cert=NULL;if(report("certificate",SecIdentityCopyCertificate((SecIdentityRef)ident,&cert)))return 1;
    SecPolicyRef policy=SecPolicyCreateWithProperties(kSecPolicyAppleCodeSigning,NULL);SecTrustRef trust=NULL;
    if(report("trust-create",SecTrustCreateWithCertificates(cert,policy,&trust)))return 1;
    SecTrustResultType result=0;OSStatus s=SecTrustEvaluate(trust,&result);report("trust-evaluate",s);printf("CERTIFICATE_PREFLIGHT trust-result %u\n",(unsigned)result);
    if(s)return 1;
    CFArrayRef chain=NULL;CSSM_TP_APPLE_EVIDENCE_INFO *info=NULL;
    s=SecTrustGetResult(trust,&result,&chain,&info);report("trust-get-result",s);printf("CERTIFICATE_PREFLIGHT chain-count %ld\n",chain?(long)CFArrayGetCount(chain):-1L);if(s)return 1;
    CMSEncoderRef encoder=NULL;if(report("cms-create",CMSEncoderCreate(&encoder)))return 1;
    if(report("cms-chain-mode",CMSEncoderSetCertificateChainMode(encoder,kCMSCertificateChainWithRootOrFail)))return 1;
    if(report("cms-add-signers",CMSEncoderAddSigners(encoder,ident)))return 1;
    if(report("cms-detached",CMSEncoderSetHasDetachedContent(encoder,true)))return 1;
    const char content[]="Linuxcode native certificate CMS preflight";
    if(report("cms-update",CMSEncoderUpdateContent(encoder,content,sizeof(content)-1)))return 1;
    CFDataRef encoded=NULL;if(report("cms-copy",CMSEncoderCopyEncodedContent(encoder,&encoded)))return 1;
    FILE *file=fopen(argv[1],"wb");if(!file)return 1;
    size_t n=fwrite(CFDataGetBytePtr(encoded),1,CFDataGetLength(encoded),file);int closed=fclose(file);
    if(n!=(size_t)CFDataGetLength(encoded)||closed)return 1;
    printf("CERTIFICATE_PREFLIGHT CMS_WRITTEN %lu\n",(unsigned long)n);return 0;
}
