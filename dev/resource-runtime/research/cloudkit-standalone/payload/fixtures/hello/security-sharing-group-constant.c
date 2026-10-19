#include <CoreFoundation/CoreFoundation.h>
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    assert(argc == 4);
    void *security = dlopen("/System/Library/Frameworks/Security.framework/Versions/A/Security",
                            RTLD_LAZY | RTLD_LOCAL | RTLD_FIRST);
    assert(security);
    CFStringRef const *slot = dlsym(security, "kSecAttrSharingGroup");
    if (!strcmp(argv[3], "missing")) {
        assert(!slot);
        puts("SECURITY_SHARING_IDENTIFIER_ABSENT_CONTROL_OK");
        return 0;
    }
    assert(!strcmp(argv[3], "present") && slot && *slot);
    void *provider = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL | RTLD_FIRST);
    assert(provider && slot == dlsym(provider, "kSecAttrSharingGroup"));
    assert(CFGetTypeID(*slot) == CFStringGetTypeID());
    CFStringRef expected = CFStringCreateWithCString(NULL, argv[2], kCFStringEncodingASCII);
    assert(expected && CFEqual(*slot, expected) && CFHash(*slot) == CFHash(expected));
    CFMutableStringRef copy = CFStringCreateMutableCopy(NULL, 0, *slot);
    assert(copy);
    CFStringAppend(copy, CFSTR("-copy"));
    assert(!CFEqual(copy, *slot) && CFEqual(*slot, expected));
    CFMutableDictionaryRef dictionary = CFDictionaryCreateMutable(NULL, 0,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    assert(dictionary);
    CFDictionarySetValue(dictionary, *slot, expected);
    assert(CFDictionaryGetValue(dictionary, expected) == expected);
    CFRelease(dictionary);
    CFRelease(copy);
    CFRelease(expected);
    puts("SECURITY_SHARING_IDENTIFIER_TYPE_VALUE_COPY_DICTIONARY_OK");
    return 0;
}
