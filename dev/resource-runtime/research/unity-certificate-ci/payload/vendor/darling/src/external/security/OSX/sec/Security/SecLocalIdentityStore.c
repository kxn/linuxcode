/* Opt-in read-only identity store for headless Linuxcode builds.
 * Native Security objects and cryptography remain in the Security backend.
 * This is not a keychain daemon, certificate trust evaluator or encrypted store.
 */
#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

extern SecIdentityRef SecIdentityCreate(CFAllocatorRef, SecCertificateRef, SecKeyRef);
extern bool SecCertificateIsValid(SecCertificateRef, CFAbsoluteTime);
extern bool SecCertificateHasUnknownCriticalExtension(SecCertificateRef);
extern SecKeyUsage SecCertificateGetKeyUsage(SecCertificateRef);
extern CFArrayRef SecCertificateCopyExtendedKeyUsage(SecCertificateRef);
extern CFDataRef SecCertificateCopyNormalizedIssuerSequence(SecCertificateRef);
extern CFDataRef SecCertificateCopyNormalizedSubjectSequence(SecCertificateRef);
#define BACKEND "/usr/lib/libDarlingLocalIdentitySecurityBackend.dylib"
static int same(CFTypeRef a, CFTypeRef b) { return a && b && CFEqual(a,b); }
static int istype(CFTypeRef a, CFTypeID t) { return a && CFGetTypeID(a)==t; }
static int flag(CFDictionaryRef d, CFStringRef k) { return same(CFDictionaryGetValue(d,k),kCFBooleanTrue); }

/* Local leaf eligibility only: no anchors, chain trust or provisioning claim.
 * Restrict policy queries to the unmodified code-signing/basic constructors. */
static OSStatus leaf_policy(CFTypeRef policy, SecCertificateRef cert, int *matches) {
    *matches=1;if(!policy)return errSecSuccess;
    if(!istype(policy,SecPolicyGetTypeID()))return errSecParam;
    CFDictionaryRef props=SecPolicyCopyProperties((SecPolicyRef)policy);
    if(!props)return errSecParam;
    CFTypeRef oid=CFDictionaryGetValue(props,kSecPolicyOid);
    int code=same(oid,kSecPolicyAppleCodeSigning);
    int basic=same(oid,kSecPolicyAppleX509Basic);
    int supported=CFDictionaryGetCount(props)==1&&(code||basic);
    CFRelease(props);if(!supported)return errSecParam;
    if(!cert)return errSecSuccess;
    *matches=SecCertificateIsValid(cert,CFAbsoluteTimeGetCurrent())&&
             !SecCertificateHasUnknownCriticalExtension(cert);
    if(code){
        SecKeyUsage usage=SecCertificateGetKeyUsage(cert)&kSecKeyUsageAll;
        if(usage&&!(usage&(kSecKeyUsageDigitalSignature|kSecKeyUsageNonRepudiation)))*matches=0;
        const UInt8 bytes[]={0x2b,6,1,5,5,7,3,3}; /* id-kp-codeSigning */
        CFDataRef wanted=CFDataCreate(NULL,bytes,sizeof bytes);
        CFArrayRef eku=SecCertificateCopyExtendedKeyUsage(cert);int found=0;
        if(eku){for(CFIndex i=0;i<CFArrayGetCount(eku);i++)found|=same(CFArrayGetValueAtIndex(eku,i),wanted);CFRelease(eku);}
        CFRelease(wanted);if(!found)*matches=0;
    }
    return errSecSuccess;
}

static OSStatus read_store(const char *path, CFDictionaryRef *out) {
    int fd=open(path,O_RDONLY|O_NOFOLLOW); if(fd<0)return errSecNotAvailable;
    struct stat st;
    if(fstat(fd,&st)||!S_ISREG(st.st_mode)||(st.st_mode&0077)||st.st_size<=0||st.st_size>16*1024*1024){close(fd);return errSecNotAvailable;}
    CFMutableDataRef data=CFDataCreateMutable(NULL,st.st_size);
    if(!data){close(fd);return errSecAllocate;}
    CFDataSetLength(data,st.st_size); size_t offset=0;
    while(offset<(size_t)st.st_size){ssize_t n=read(fd,CFDataGetMutableBytePtr(data)+offset,st.st_size-offset);if(n<=0){close(fd);CFRelease(data);return errSecDecode;}offset+=n;}
    close(fd);
    CFPropertyListRef root=CFPropertyListCreateWithData(NULL,data,kCFPropertyListImmutable,NULL,NULL);CFRelease(data);
    if(!istype(root,CFDictionaryGetTypeID())){if(root)CFRelease(root);return errSecDecode;}
    int version=0;CFTypeRef v=CFDictionaryGetValue(root,CFSTR("version"));
    if(!istype(v,CFNumberGetTypeID())||!CFNumberGetValue(v,kCFNumberIntType,&version)||version!=1||!istype(CFDictionaryGetValue(root,CFSTR("items")),CFArrayGetTypeID())||!istype(CFDictionaryGetValue(root,CFSTR("locked")),CFBooleanGetTypeID())){CFRelease(root);return errSecDecode;}
    if(flag(root,CFSTR("locked"))){CFRelease(root);return errSecInteractionNotAllowed;}
    *out=root;return errSecSuccess;
}

/* Supply candidate parents from the explicit local store.  Subject/issuer
 * matching does not confer trust: trustd still checks signatures and anchors. */
CFArrayRef SecItemCopyParentCertificates_osx(SecCertificateRef certificate, void *context) {
    const char *path=getenv("LINUXCODE_IDENTITY_STORE");
    if(!path||!*path){
        void *backend=dlopen(BACKEND,RTLD_NOW|RTLD_LOCAL);
        __typeof__(&SecItemCopyParentCertificates_osx) original=backend?dlsym(backend,"SecItemCopyParentCertificates_osx"):NULL;
        return original?original(certificate,context):NULL;
    }
    if(!certificate||CFGetTypeID(certificate)!=SecCertificateGetTypeID())return NULL;
    CFDictionaryRef store=NULL;if(read_store(path,&store))return NULL;
    CFDataRef issuer=SecCertificateCopyNormalizedIssuerSequence(certificate);
    CFMutableArrayRef parents=CFArrayCreateMutable(NULL,0,&kCFTypeArrayCallBacks);
    CFArrayRef items=CFDictionaryGetValue(store,CFSTR("items"));int malformed=0;
    for(CFIndex i=0;parents&&i<CFArrayGetCount(items);i++){
        CFTypeRef record=CFArrayGetValueAtIndex(items,i);
        CFTypeRef der=istype(record,CFDictionaryGetTypeID())?CFDictionaryGetValue(record,CFSTR("certificate")):NULL;
        SecCertificateRef parent=istype(der,CFDataGetTypeID())?SecCertificateCreateWithData(NULL,der):NULL;
        if(!parent){malformed=1;break;}
        CFDataRef subject=SecCertificateCopyNormalizedSubjectSequence(parent);
        if(same(issuer,subject))CFArrayAppendValue(parents,parent);
        if(subject)CFRelease(subject);CFRelease(parent);
    }
    if(issuer)CFRelease(issuer);CFRelease(store);
    if(malformed&&parents){CFRelease(parents);parents=NULL;}
    if(getenv("LINUXCODE_IDENTITY_TRACE"))fprintf(stderr,"LOCAL_IDENTITY_PARENT_CANDIDATES %ld\n",parents?(long)CFArrayGetCount(parents):-1L);
    return parents;
}

/* Version 1 stores identities, but has no persisted preference records.  An
 * absent preference must let callers continue their explicit identity search,
 * without entering the unrelated legacy SecurityServer database. */
OSStatus SecIdentityCopyPreference(CFStringRef name, CSSM_KEYUSE usage,
                                  CFArrayRef issuers, SecIdentityRef *result) {
    if(result)*result=NULL;
    const char *path=getenv("LINUXCODE_IDENTITY_STORE");
    if(!path||!*path){
        void *backend=dlopen(BACKEND,RTLD_NOW|RTLD_LOCAL);
        __typeof__(&SecIdentityCopyPreference) original=backend?dlsym(backend,"SecIdentityCopyPreference"):NULL;
        return original?original(name,usage,issuers,result):errSecNotAvailable;
    }
    if(!result||!istype(name,CFStringGetTypeID())||
       (issuers&&!istype(issuers,CFArrayGetTypeID())))return errSecParam;
    CFDictionaryRef store=NULL;OSStatus status=read_store(path,&store);
    if(store)CFRelease(store);
    if(getenv("LINUXCODE_IDENTITY_TRACE"))fprintf(stderr,"LOCAL_IDENTITY_PREFERENCE_RESULT %d\n",(int)(status?status:errSecItemNotFound));
    return status?status:errSecItemNotFound;
}

/* Validate both halves before constructing a real native identity. */
static OSStatus identity(CFDictionaryRef record, SecCertificateRef *cert, SecKeyRef *key, SecIdentityRef *ident) {
    if(!istype(record,CFDictionaryGetTypeID()))return errSecDecode;
    CFTypeRef der=CFDictionaryGetValue(record,CFSTR("certificate")),raw=CFDictionaryGetValue(record,CFSTR("privateKey"));
    CFTypeRef label=CFDictionaryGetValue(record,CFSTR("label"));
    if(!istype(der,CFDataGetTypeID())||!istype(raw,CFDataGetTypeID())||!istype(label,CFStringGetTypeID()))return errSecDecode;
    *cert=SecCertificateCreateWithData(NULL,der);if(!*cert)return errSecDecode;
    const void *ks[]={kSecAttrKeyType,kSecAttrKeyClass};const void *vs[]={kSecAttrKeyTypeRSA,kSecAttrKeyClassPrivate};
    CFDictionaryRef attrs=CFDictionaryCreate(NULL,ks,vs,2,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    *key=SecKeyCreateWithData(raw,attrs,NULL);CFRelease(attrs);if(!*key)return errSecDecode;
    SecKeyRef a=SecCertificateCopyKey(*cert),b=SecKeyCopyPublicKey(*key);
    CFDataRef x=a?SecKeyCopyExternalRepresentation(a,NULL):NULL,y=b?SecKeyCopyExternalRepresentation(b,NULL):NULL;
    int match=same(x,y);if(x)CFRelease(x);if(y)CFRelease(y);if(a)CFRelease(a);if(b)CFRelease(b);
    if(!match)return errSecDecode;
    *ident=SecIdentityCreate(NULL,*cert,*key);return *ident?errSecSuccess:errSecAllocate;
}

/* Xcode resolves an enumerated certificate back to its signing identity with
 * this legacy API. Search the opted-in default store by public key, including
 * renewed certificates using the same key, then return a real native identity
 * containing the caller's certificate. Explicit native keychain scopes retain
 * their original implementation. No trust or policy decision is made here. */
OSStatus SecIdentityCreateWithCertificate(CFTypeRef keychainOrArray,
                                         SecCertificateRef certificate,
                                         SecIdentityRef *result) {
    if(result)*result=NULL;
    const char *path=getenv("LINUXCODE_IDENTITY_STORE");
    if(!path||!*path||keychainOrArray){
        void *backend=dlopen(BACKEND,RTLD_NOW|RTLD_LOCAL);
        __typeof__(&SecIdentityCreateWithCertificate) original=backend?dlsym(backend,"SecIdentityCreateWithCertificate"):NULL;
        return original?original(keychainOrArray,certificate,result):errSecNotAvailable;
    }
    if(!result||!istype(certificate,SecCertificateGetTypeID()))return errSecParam;
    CFDictionaryRef store=NULL;OSStatus status=read_store(path,&store);if(status)return status;
    SecKeyRef wanted=SecCertificateCopyKey(certificate);
    CFDataRef wantedBytes=wanted?SecKeyCopyExternalRepresentation(wanted,NULL):NULL;
    if(wanted)CFRelease(wanted);
    if(!wantedBytes){CFRelease(store);return errSecDecode;}
    CFArrayRef items=CFDictionaryGetValue(store,CFSTR("items"));status=errSecItemNotFound;
    for(CFIndex i=0;i<CFArrayGetCount(items);i++){
        SecCertificateRef cert=NULL;SecKeyRef key=NULL;SecIdentityRef ident=NULL;
        OSStatus itemStatus=identity(CFArrayGetValueAtIndex(items,i),&cert,&key,&ident);
        if(!itemStatus){
            SecKeyRef pub=SecKeyCopyPublicKey(key);
            CFDataRef bytes=pub?SecKeyCopyExternalRepresentation(pub,NULL):NULL;
            if(same(bytes,wantedBytes)){
                *result=SecIdentityCreate(NULL,certificate,key);
                status=*result?errSecSuccess:errSecAllocate;
            }
            if(bytes)CFRelease(bytes);if(pub)CFRelease(pub);
        }else status=itemStatus;
        if(ident)CFRelease(ident);if(key)CFRelease(key);if(cert)CFRelease(cert);
        if(*result||itemStatus)break;
    }
    CFRelease(wantedBytes);CFRelease(store);
    if(getenv("LINUXCODE_IDENTITY_TRACE"))fprintf(stderr,"LOCAL_IDENTITY_CERTIFICATE_LOOKUP_RESULT %d\n",(int)status);
    return status;
}

OSStatus SecItemCopyMatching(CFDictionaryRef query, CFTypeRef *result) {
    if(result)*result=NULL;
    const char *path=getenv("LINUXCODE_IDENTITY_STORE");
    if(!path||!*path){
        void *backend=dlopen(BACKEND,RTLD_NOW|RTLD_LOCAL);
        __typeof__(&SecItemCopyMatching) original=backend?dlsym(backend,"SecItemCopyMatching"):NULL;
        return original?original(query,result):errSecNotAvailable;
    }
    if(!istype(query,CFDictionaryGetTypeID()))return errSecParam;
    CFIndex count=CFDictionaryGetCount(query);const void **keys=calloc(count?count:1,sizeof(void*));
    if(!keys)return errSecAllocate;CFDictionaryGetKeysAndValues(query,keys,NULL);
    int unsupported=0;
    for(CFIndex i=0;i<count;i++){
        CFTypeRef k=keys[i];
        if(getenv("LINUXCODE_IDENTITY_TRACE")){char text[256];if(istype(k,CFStringGetTypeID())&&CFStringGetCString(k,text,sizeof text,kCFStringEncodingUTF8))fprintf(stderr,"LOCAL_IDENTITY_QUERY_KEY %s\n",text);}
        if(!same(k,kSecClass)&&!same(k,kSecAttrLabel)&&!same(k,kSecMatchLimit)&&!same(k,kSecReturnRef)&&!same(k,kSecReturnData)&&!same(k,kSecReturnAttributes)&&!same(k,kSecUseAuthenticationUI)&&!same(k,kSecMatchPolicy)&&!same(k,kSecAttrCanSign))unsupported=1;
    }
    free(keys);
    if(getenv("LINUXCODE_IDENTITY_TRACE")){
        CFTypeRef policy=CFDictionaryGetValue(query,kSecMatchPolicy);
        if(policy&&CFGetTypeID(policy)==SecPolicyGetTypeID()){
            CFDictionaryRef props=SecPolicyCopyProperties((SecPolicyRef)policy);
            if(props){CFShow(props);CFRelease(props);}
        }
    }
    if(unsupported)return errSecParam;
    CFTypeRef policy=CFDictionaryGetValue(query,kSecMatchPolicy),canSign=CFDictionaryGetValue(query,kSecAttrCanSign);
    if(canSign&&!istype(canSign,CFBooleanGetTypeID()))return errSecParam;
    int eligible;OSStatus policyStatus=leaf_policy(policy,NULL,&eligible);if(policyStatus)return policyStatus;
    CFTypeRef cls=CFDictionaryGetValue(query,kSecClass),limit=CFDictionaryGetValue(query,kSecMatchLimit),label=CFDictionaryGetValue(query,kSecAttrLabel);
    if(!same(cls,kSecClassIdentity)&&!same(cls,kSecClassCertificate)&&!same(cls,kSecClassKey))return errSecParam;
    if(limit&&!same(limit,kSecMatchLimitOne)&&!same(limit,kSecMatchLimitAll))return errSecParam;
    if(label&&!istype(label,CFStringGetTypeID()))return errSecParam;
    CFStringRef boolkeys[]={kSecReturnRef,kSecReturnData,kSecReturnAttributes};
    for(unsigned i=0;i<3;i++){CFTypeRef v=CFDictionaryGetValue(query,boolkeys[i]);if(v&&!istype(v,CFBooleanGetTypeID()))return errSecParam;}
    int ref=flag(query,kSecReturnRef),data=flag(query,kSecReturnData),attributes=flag(query,kSecReturnAttributes);
    /* Private-key export and identity data have no implemented representation. */
    if(data&&!same(cls,kSecClassCertificate))return errSecParam;
    CFDictionaryRef store=NULL;OSStatus status=read_store(path,&store);if(status)return status;
    CFArrayRef items=CFDictionaryGetValue(store,CFSTR("items"));CFMutableArrayRef matches=CFArrayCreateMutable(NULL,0,&kCFTypeArrayCallBacks);
    for(CFIndex i=0;i<CFArrayGetCount(items);i++){
        SecCertificateRef cert=NULL;SecKeyRef key=NULL;SecIdentityRef ident=NULL;
        CFDictionaryRef item=CFArrayGetValueAtIndex(items,i);status=identity(item,&cert,&key,&ident);
        eligible=1;
        if(!status)status=leaf_policy(policy,cert,&eligible);
        if(!status&&canSign){
            CFDictionaryRef attrs=SecKeyCopyAttributes(key);
            int actual=attrs&&same(CFDictionaryGetValue(attrs,kSecAttrCanSign),kCFBooleanTrue);
            if(attrs)CFRelease(attrs);if(actual!=same(canSign,kCFBooleanTrue))eligible=0;
        }
        if(!status&&eligible&&(!label||same(label,CFDictionaryGetValue(item,CFSTR("label"))))){
            CFTypeRef object=same(cls,kSecClassIdentity)?(CFTypeRef)ident:same(cls,kSecClassCertificate)?(CFTypeRef)cert:(CFTypeRef)key;
            CFDataRef der=data?SecCertificateCopyData(cert):NULL;
            CFTypeRef value=NULL;
            if(attributes||(ref&&data)){
                CFMutableDictionaryRef d=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
                if(attributes){CFDictionarySetValue(d,kSecClass,cls);CFDictionarySetValue(d,kSecAttrLabel,CFDictionaryGetValue(item,CFSTR("label")));}
                if(ref)CFDictionarySetValue(d,kSecValueRef,object);if(data)CFDictionarySetValue(d,kSecValueData,der);value=d;
            }else value=CFRetain(ref?object:data?(CFTypeRef)der:(CFTypeRef)kCFBooleanTrue);
            CFArrayAppendValue(matches,value);CFRelease(value);if(der)CFRelease(der);
        }
        if(ident)CFRelease(ident);if(key)CFRelease(key);if(cert)CFRelease(cert);
        if(status)break;
    }
    if(!status&&!CFArrayGetCount(matches))status=errSecItemNotFound;
    if(!status&&result&&(ref||data||attributes))*result=CFRetain(same(limit,kSecMatchLimitAll)?(CFTypeRef)matches:CFArrayGetValueAtIndex(matches,0));
    if(getenv("LINUXCODE_IDENTITY_TRACE"))fprintf(stderr,"LOCAL_IDENTITY_QUERY_RESULT %d MATCHES %ld\n",(int)status,(long)CFArrayGetCount(matches));
    CFRelease(matches);CFRelease(store);return status;
}
