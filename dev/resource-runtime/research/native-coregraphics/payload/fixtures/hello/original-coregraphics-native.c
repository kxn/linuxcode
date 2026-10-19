#include <CoreGraphics/CoreGraphics.h>
#include <simd/matrix_types.h>
#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    setbuf(stdout, NULL);
    assert(!getenv("DISPLAY") && !getenv("WAYLAND_DISPLAY") && !getenv("XAUTHORITY"));
    _Static_assert(sizeof(simd_double3x3) == 96, "SDK matrix size");
    _Static_assert(_Alignof(simd_double3x3) == 16, "SDK matrix alignment");
    const double *matrix = dlsym(RTLD_DEFAULT, "matrix_identity_double3x3");
    assert(matrix && ((uintptr_t)matrix % _Alignof(simd_double3x3)) == 0);
    Dl_info owner;
    assert(dladdr(matrix, &owner) && strstr(owner.dli_fname, "libDarlingSIMDDoubleMatrix.dylib"));
    const double expected[] = {1,0,0,0,0,1,0,0,0,0,1,0};
    assert(!memcmp(matrix, expected, sizeof(expected)));
    const double inputs[][3] = {{2,-3,4}, {-0.5,0.25,65536}, {0,0,0}};
    for (unsigned n = 0; n < 3; ++n)
        for (unsigned row = 0; row < 3; ++row) {
            double result = 0;
            for (unsigned col = 0; col < 3; ++col) result += matrix[col*4+row]*inputs[n][col];
            assert(result == inputs[n][row]);
        }
    puts("ORIGINAL_CG_NATIVE_SIMD_LAYOUT_AND_VALUES_OK");
    assert(dladdr((void *)CGColorSpaceCreateDeviceRGB, &owner));
    assert(strstr(owner.dli_fname, "/coregraphics-native-"));
    void *convert = dlsym(RTLD_DEFAULT, "CGColorTransformConvertImage");
    assert(convert && dladdr(convert, &owner) && strstr(owner.dli_fname, "/coregraphics-native-"));
    printf("ORIGINAL_CG_NATIVE_IMPLEMENTATION_OWNER %s\n", owner.dli_fname);
    CGColorSpaceRef rgb = CGColorSpaceCreateDeviceRGB();
    assert(rgb && CGColorSpaceGetModel(rgb) == kCGColorSpaceModelRGB);
    assert(CGColorSpaceGetNumberOfComponents(rgb) == 3);
    assert(CFGetTypeID(rgb) == CGColorSpaceGetTypeID());
    puts("ORIGINAL_CG_NATIVE_DEVICE_RGB_OK");
    unsigned char bytes[16] = {0};
    CGContextRef context = CGBitmapContextCreate(bytes, 2, 2, 8, 8, rgb,
        kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    assert(context && CGBitmapContextGetData(context) == bytes);
    CGContextSetRGBFillColor(context, 1., 0., 0., 1.);
    CGContextFillRect(context, CGRectMake(0, 0, 2, 2));
    for (unsigned i = 0; i < 4; ++i) {
        assert(bytes[4*i] == 255 && bytes[4*i+1] == 0 && bytes[4*i+2] == 0 && bytes[4*i+3] == 255);
    }
    CGImageRef image = CGBitmapContextCreateImage(context);
    assert(image && CGImageGetWidth(image) == 2 && CGImageGetHeight(image) == 2);
    CGDataProviderRef provider = CGImageGetDataProvider(image);
    CFDataRef data = CGDataProviderCopyData(provider);
    assert(data && CFDataGetLength(data) >= 16 && !memcmp(CFDataGetBytePtr(data), bytes, 16));
    CFRelease(data);
    CGImageRelease(image);
    CGContextRelease(context);
    CGColorSpaceRelease(rgb);
    puts("ORIGINAL_CG_NATIVE_BITMAP_PIXELS_AND_IMAGE_DATA_OK");
    return 0;
}
