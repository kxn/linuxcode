#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>
#include <assert.h>
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void png(void) {
    const char *path = "/Volumes/SystemRoot/workspace/runtime/imageio-fixtures/test.png";
    CFURLRef url = CFURLCreateFromFileSystemRepresentation(NULL, (const UInt8 *)path, strlen(path), false);
    assert(url);
    CGImageSourceRef source = CGImageSourceCreateWithURL(url, NULL);
    assert(source && CGImageSourceGetCount(source) == 1);
    assert(CFEqual(CGImageSourceGetType(source), CFSTR("public.png")));
    CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, NULL);
    assert(image && CGImageGetWidth(image) == 13 && CGImageGetHeight(image) == 7);
    assert(CGImageGetBitsPerComponent(image) == 8);
    printf("ORIGINAL_CG_NATIVE_PNG_FORMAT bits=%zu alpha=%u bitmap=%x row=%zu\n", CGImageGetBitsPerPixel(image), (unsigned)CGImageGetAlphaInfo(image), (unsigned)CGImageGetBitmapInfo(image), CGImageGetBytesPerRow(image));
    CFDataRef data = CGDataProviderCopyData(CGImageGetDataProvider(image));
    assert(data);
    size_t row = CGImageGetBytesPerRow(image);
    assert(row >= 13*4 && CFDataGetLength(data) >= row*7);
    const UInt8 *bytes = CFDataGetBytePtr(data);
    printf("ORIGINAL_CG_NATIVE_PNG_FIRST_BYTES");
    for (unsigned k=0;k<16;++k) printf(" %02x",bytes[k]);
    puts("");
    /* Original ImageIO expands this opaque RGB PNG to RGBX storage. */
    assert(CGImageGetBitsPerPixel(image) == 32);
    assert(CGImageGetAlphaInfo(image) == kCGImageAlphaNoneSkipLast);
    assert((CGImageGetBitmapInfo(image)&kCGBitmapByteOrderMask) == kCGBitmapByteOrderDefault);
    for (unsigned y=0; y<7; ++y) for (unsigned x=0; x<13; ++x) {
        assert(bytes[row*y+x*4] == 200 && bytes[row*y+x*4+1] == 30 && bytes[row*y+x*4+2] == 90);
    }
    CFRelease(data); CGImageRelease(image); CFRelease(source); CFRelease(url);
    puts("ORIGINAL_CG_NATIVE_PNG_91_PIXELS_INDEPENDENTLY_MATCHED");
}
static void color(void) {
    void *backend = dlopen("/System/Library/Frameworks/ColorSync.framework/ColorSync", RTLD_LAZY|RTLD_LOCAL);
    if (!backend) printf("ORIGINAL_CG_NATIVE_COLORSYNC_LOAD_ERROR %s\n", dlerror());
    else {
        void *transform = dlsym(backend,"ColorSyncTransformCreate");
        Dl_info owner;
        assert(transform && dladdr(transform,&owner));
        printf("ORIGINAL_CG_NATIVE_COLORSYNC_OWNER %s\n",owner.dli_fname);
    }
    CGColorSpaceRef srgb = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    CGColorSpaceRef linear = CGColorSpaceCreateWithName(kCGColorSpaceLinearSRGB);
    CGColorSpaceRef p3 = CGColorSpaceCreateWithName(kCGColorSpaceDisplayP3);
    assert(srgb && linear && p3);
    bool (*wide)(CGColorSpaceRef) = dlsym(RTLD_DEFAULT,"CGColorSpaceIsWideGamutRGB");
    assert(wide && !wide(srgb) && wide(p3));
    CFDataRef icc = CGColorSpaceCopyICCData(p3);
    assert(icc && CFDataGetLength(icc) > 128 && !memcmp(CFDataGetBytePtr(icc)+36,"acsp",4));
    CFRelease(icc);
    puts("ORIGINAL_CG_NATIVE_SRGB_LINEAR_P3_AND_REAL_ICC_OK");
    CGColorConversionInfoRef info = CGColorConversionInfoCreate(srgb, linear);
    assert(info);
    const float input[] = {0.5f, 0.25f, 0.75f, 1.f, 0.f, 1.f, 0.04045f, 1.f};
    float output[8] = {0};
    CGColorBufferFormat format = {0, kCGImageAlphaLast|kCGBitmapFloatComponents|kCGBitmapByteOrder32Little, 32, 128, sizeof(input)};
    assert(CGColorConversionInfoConvertData(info, 2, 1, output, format, input, format, NULL));
    for (unsigned n=0; n<2; ++n) {
        for (unsigned c=0; c<3; ++c) {
            double v = input[n*4+c];
            double expected = v <= 0.04045 ? v/12.92 : pow((v+0.055)/1.055,2.4);
            printf("ORIGINAL_CG_NATIVE_LINEAR_SAMPLE %u %.9g %.9g\n",n*4+c,output[n*4+c],expected);
            assert(fabs(output[n*4+c]-expected) < 0.003);
        }
        assert(fabs(output[n*4+3]-1.f)<1e-6);
    }
    CFRelease(info); CGColorSpaceRelease(srgb); CGColorSpaceRelease(linear); CGColorSpaceRelease(p3);
    puts("ORIGINAL_CG_NATIVE_COLOR_CONVERSION_MATCHES_INDEPENDENT_SRGB_FORMULA");
}
int main(int argc,char **argv) {
    setbuf(stdout,NULL);
    Dl_info owner;
    assert(dladdr((void *)CGColorSpaceCreateWithName,&owner) && strstr(owner.dli_fname,"/coregraphics-native-"));
    assert(dladdr((void *)CGImageSourceCreateImageAtIndex,&owner) && strstr(owner.dli_fname,"/imageio-legacy-key/frameworks/ImageIO.framework/"));
    assert(argc==2);
    if (!strcmp(argv[1],"png")) png();
    else if (!strcmp(argv[1],"color")) color();
    else return 2;
    return 0;
}
