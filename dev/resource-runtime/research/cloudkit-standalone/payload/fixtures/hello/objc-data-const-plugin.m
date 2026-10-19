#include <assert.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <objc/runtime.h>
#include <objc/message.h>

// Deliberately uncanonicalized references in a segment sealed before objc maps it.
__attribute__((used, section("__DATA_CONST,__objc_selrefs")))
static SEL references[] = {(SEL)"linuxcodeDataConstValue:", (SEL)"linuxcodeDataConstOther:"};

__attribute__((objc_root_class))
@interface LinuxcodeDataConstProbe
- (long)linuxcodeDataConstValue:(long)value;
@end
@implementation LinuxcodeDataConstProbe
- (long)linuxcodeDataConstValue:(long)value { return value * 7 + 3; }
@end

SEL *linuxcode_data_const_refs(void) { return references; }
long linuxcode_data_const_dispatch(long value) {
    id object = class_createInstance(objc_getClass("LinuxcodeDataConstProbe"), 0);
    assert(object);
    long result = ((long (*)(id, SEL, long))objc_msgSend)(object, references[0], value);
    object_dispose(object);
    return result;
}
