#include <CoreGraphics/CoreGraphics.h>
#include <assert.h>
#include <stdio.h>
#include <dlfcn.h>
#include <string.h>
int main(void) {
    assert(!CGColorSpaceGetName(NULL));
    assert(!CGColorSpaceCopyName(NULL));
    CGColorSpaceRef rgb = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    assert(rgb && CGColorSpaceGetModel(rgb) == kCGColorSpaceModelRGB);
    CFStringRef borrowed = CGColorSpaceGetName(rgb);
    assert(borrowed && CFEqual(borrowed, kCGColorSpaceSRGB));
    CFStringRef copied = CGColorSpaceCopyName(rgb);
    assert(copied && CFEqual(copied, kCGColorSpaceSRGB));
    CGColorSpaceRelease(rgb);
    assert(CFStringGetLength(copied) > 0 && CFEqual(copied, kCGColorSpaceSRGB));
    CFRelease(copied);
    CGColorSpaceRef device = CGColorSpaceCreateDeviceRGB();
    assert(device && CFEqual(CGColorSpaceGetName(device), CFSTR("kCGColorSpaceDeviceRGB")));
    copied = CGColorSpaceCopyName(device); assert(copied && CFEqual(copied, CFSTR("kCGColorSpaceDeviceRGB"))); CFRelease(copied);
    CGColorSpaceRelease(device);
    CGColorSpaceRef p3 = CGColorSpaceCreateWithName(kCGColorSpaceDisplayP3);
    assert(p3 && CFEqual(CGColorSpaceGetName(p3), kCGColorSpaceDisplayP3));
    copied = CGColorSpaceCopyName(p3); CGColorSpaceRelease(p3);
    assert(copied && CFEqual(copied, kCGColorSpaceDisplayP3)); CFRelease(copied);
    CGColorSpaceRef gray = CGColorSpaceCreateDeviceGray(), cmyk = CGColorSpaceCreateDeviceCMYK();
    assert(gray && CFEqual(CGColorSpaceGetName(gray), CFSTR("kCGColorSpaceDeviceGray")));
    assert(cmyk && CFEqual(CGColorSpaceGetName(cmyk), CFSTR("kCGColorSpaceDeviceCMYK")));
    CGColorSpaceRelease(gray); CGColorSpaceRelease(cmyk);
    assert(!CGColorSpaceCreateWithName(CFSTR("unsupported fixture profile")));
    Dl_info owner; assert(dladdr((void*)CGColorSpaceCopyName, &owner));
    assert(strstr(owner.dli_fname, "/cg-colorspace-names-v2/frameworks/CoreGraphics.framework/"));
    printf("CG_COLORSPACE_NAMES_ACTUAL_SOURCE_OWNER %s\n", owner.dli_fname);
    puts("CG_COLORSPACE_NAMES_REAL_SRGB_COPY_LIFETIME_DEVICE_AND_NULL_CASES_OK");
    return 0;
}
