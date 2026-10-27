#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
extern SecPolicyRef SecPolicyCreateAppleExternalDeveloper(void);
int main(int argc,char **argv){
    setbuf(stdout,NULL);if(argc!=2&&argc!=3)return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 3;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);
    UInt8 *p=malloc(n);if(!p||fread(p,1,n,f)!=(size_t)n)return 4;fclose(f);
    CFDataRef bytes=CFDataCreate(NULL,p,n);free(p);
    CFDictionaryRef store=(CFDictionaryRef)CFPropertyListCreateWithData(NULL,bytes,kCFPropertyListImmutable,NULL,NULL);
    CFArrayRef items=CFDictionaryGetValue(store,CFSTR("items"));
    SecCertificateRef leaf=SecCertificateCreateWithData(NULL,CFDictionaryGetValue(CFArrayGetValueAtIndex(items,0),CFSTR("certificate")));
    SecPolicyRef policy=SecPolicyCreateWithProperties(kSecPolicyAppleCodeSigning,NULL);SecTrustRef trust=NULL;
    CFArrayRef policies=NULL;SecPolicyRef developer=NULL,revocation=NULL;
    if(argc==3){developer=SecPolicyCreateAppleExternalDeveloper();revocation=SecPolicyCreateRevocation(0x23);
        if(!developer||!revocation)return 7;
        policies=CFArrayCreate(NULL,(const void*[]){developer,revocation},2,&kCFTypeArrayCallBacks);}
    if(SecTrustCreateWithCertificates(leaf,policies?(CFTypeRef)policies:(CFTypeRef)policy,&trust))return 5;
    printf("UNANCHORED_TRUST_BEGIN\n");sleep(5);
    CFErrorRef error=NULL;Boolean ok=SecTrustEvaluateWithError(trust,&error);
    printf("UNANCHORED_TRUST_RETURN accepted=%d error=%ld\n",ok,error?(long)CFErrorGetCode(error):0L);
    if(error)CFRelease(error);CFRelease(trust);CFRelease(policy);CFRelease(leaf);CFRelease(store);CFRelease(bytes);
    return ok?6:0;
}
