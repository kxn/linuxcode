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
#define BACKEND "/usr/lib/libDarlingLocalIdentitySecurityBackend.dylib"
static int same(CFTypeRef a, CFTypeRef b) { return a && b && CFEqual(a,b); }
static int istype(CFTypeRef a, CFTypeID t) { return a && CFGetTypeID(a)==t; }
static int flag(CFDictionaryRef d, CFStringRef k) { return same(CFDictionaryGetValue(d,k),kCFBooleanTrue); }

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
    for(CFIndex i=0;i<count;i++){
        CFTypeRef k=keys[i];
        if(getenv("LINUXCODE_IDENTITY_TRACE")){char text[256];if(istype(k,CFStringGetTypeID())&&CFStringGetCString(k,text,sizeof text,kCFStringEncodingUTF8))fprintf(stderr,"LOCAL_IDENTITY_QUERY_KEY %s\n",text);}
        if(!same(k,kSecClass)&&!same(k,kSecAttrLabel)&&!same(k,kSecMatchLimit)&&!same(k,kSecReturnRef)&&!same(k,kSecReturnData)&&!same(k,kSecReturnAttributes)&&!same(k,kSecUseAuthenticationUI)){free(keys);return errSecParam;}
    }
    free(keys);
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
        if(!status&&(!label||same(label,CFDictionaryGetValue(item,CFSTR("label"))))){
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
