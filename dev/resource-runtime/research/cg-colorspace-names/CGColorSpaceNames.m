/* Preserve real Onyx2D names and CoreFoundation Get/Copy ownership rules. */
#import <CoreGraphics/CGColorSpace.h>
#import <Onyx2D/O2ColorSpace.h>

@interface O2ColorSpace (DarlingColorSpaceNames)
- (CFStringRef)darlingColorSpaceName;
- (void)darlingRememberSupportedName:(CFStringRef)name;
@end
@implementation O2ColorSpace (DarlingColorSpaceNames)
- (CFStringRef)darlingColorSpaceName {
    if (_name) return _name;
    switch (_type) {
        case kO2ColorSpaceModelMonochrome: return CFSTR("kCGColorSpaceDeviceGray");
        case kO2ColorSpaceModelRGB: return CFSTR("kCGColorSpaceDeviceRGB");
        case kO2ColorSpaceModelCMYK: return CFSTR("kCGColorSpaceDeviceCMYK");
        default: return NULL;
    }
}
- (void)darlingRememberSupportedName:(CFStringRef)name {
    /* The existing O2 factory supports these two named spaces. Keep the
       canonical immutable names; do not claim to implement other profiles. */
    if (CFEqual(name, CFSTR("kCGColorSpaceSRGB"))) _name = CFSTR("kCGColorSpaceSRGB");
    else if (CFEqual(name, CFSTR("kCGColorSpaceDisplayP3"))) _name = CFSTR("kCGColorSpaceDisplayP3");
}
@end

CGColorSpaceRef CGColorSpaceCreateWithName(CFStringRef name) {
    if (!name) return NULL;
    O2ColorSpaceRef space = O2ColorSpaceCreateWithName(name);
    if (space) [space darlingRememberSupportedName:name];
    return (CGColorSpaceRef)space;
}
CFStringRef CGColorSpaceGetName(CGColorSpaceRef space) {
    return space ? [(O2ColorSpace *)space darlingColorSpaceName] : NULL;
}
CFStringRef CGColorSpaceCopyName(CGColorSpaceRef space) {
    CFStringRef name = CGColorSpaceGetName(space);
    return name ? CFStringCreateCopy(kCFAllocatorDefault, name) : NULL;
}
