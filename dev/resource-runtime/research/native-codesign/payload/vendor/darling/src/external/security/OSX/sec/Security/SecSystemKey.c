/* System-key lookup compatibility for the existing native token-key backend.
 * Object identifiers and enum values follow Apple's SecCTKKey/SecKeyPriv.
 * This requests actual token keys; it never generates replacement device keys.
 */
#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdint.h>
#include <string.h>
extern const CFStringRef kSecAttrTokenOID;
extern const CFStringRef kSecAttrTokenIDAppleKeyStore;
extern const CFStringRef kSecAttrTokenIDSecureElement;

static SecKeyRef fail(OSStatus status, CFErrorRef *error) {
    if(error)*error=CFErrorCreate(NULL,kCFErrorDomainOSStatus,status,NULL);
    return NULL;
}
SecKeyRef SecKeyCopySystemKey(uint32_t kind, CFErrorRef *error) {
    static const char *const identifiers[]={
        "com.apple.setoken.sik", "com.apple.setoken.gid",
        "com.apple.setoken.uikc", "com.apple.setoken.uikp",
        "com.apple.secelemtoken.casd", "com.apple.setoken.oikc",
        "com.apple.setoken.oikp", "com.apple.setoken.dakc",
        "com.apple.setoken.dakp", "com.apple.setoken.havenc",
        "com.apple.setoken.havenp", "com.apple.setoken.sdakc",
        "com.apple.setoken.sdakp", "com.apple.setoken.dcik"
    };
    if(kind>=sizeof(identifiers)/sizeof(identifiers[0]))return fail(errSecParam,error);
    const char *name=identifiers[kind];size_t size=strlen(name);UInt8 bytes[128];
    if(size>=126)return fail(errSecParam,error);
    bytes[0]=4;bytes[1]=(UInt8)size;memcpy(bytes+2,name,size);
    CFDataRef oid=CFDataCreate(NULL,bytes,size+2);if(!oid)return fail(errSecAllocate,error);
    const void *keys[]={kSecAttrTokenOID,kSecAttrTokenID};
    const void *values[]={oid,kind==4?kSecAttrTokenIDSecureElement:kSecAttrTokenIDAppleKeyStore};
    CFDictionaryRef attrs=CFDictionaryCreate(NULL,keys,values,2,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);CFRelease(oid);
    if(!attrs)return fail(errSecAllocate,error);
    /* SecKeyCreateWithData dispatches token-ID dictionaries to the same native
     * SecKeyCreateCTKKey used by SecKeyCopyAttestationKey, before data parsing. */
    CFDataRef empty=CFDataCreate(NULL,NULL,0);
    if(!empty){CFRelease(attrs);return fail(errSecAllocate,error);}
    SecKeyRef key=SecKeyCreateWithData(empty,attrs,error);CFRelease(empty);CFRelease(attrs);return key;
}
