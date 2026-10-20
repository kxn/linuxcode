import QuartzCore
import Darwin

let expectedProvider = CommandLine.arguments[1]
let wrongExpected = CommandLine.arguments.count > 2 && CommandLine.arguments[2] == "wrong-value"
let name = "$sSo16CAFrameRateRangeV10QuartzCoreE7minimum7maximum9preferredABSf_S2fSgtcfC"
guard let library = dlopen("/usr/lib/swift/libswiftQuartzCore.dylib", RTLD_LAZY),
      let function = dlsym(library, name) else { exit(12) }
var owner = Dl_info()
guard dladdr(function, &owner) != 0, let path = owner.dli_fname,
      String(cString: path).contains(expectedProvider) else { exit(13) }
var checks = 0
func check(_ condition: Bool) {
    checks += 1
    if !condition { exit(15) }
}
func same(_ actual: Float?, _ expected: Float?) -> Bool {
    switch (actual, expected) {
    case (nil, nil): return true
    case let (a?, b?): return (a.isNaN && b.isNaN) || a == b
    default: return false
    }
}
let cases: [(Float?, Float?)] = [(nil, nil), (60, 60), (0, nil), (-0.0, nil), (.nan, .nan), (.infinity, .infinity)]
for (input, expected) in cases {
    let range = CAFrameRateRange(minimum: 24, maximum: 120, preferred: input)
    check(range.minimum == 24)
    check(range.maximum == (wrongExpected ? 112 : 120))
    check(same(range.preferred, expected))
}
var mutable = CAFrameRateRange(minimum: 30, maximum: 144, preferred: nil)
mutable.preferred = 72
check(mutable.preferred == 72)
mutable.preferred = nil
check(mutable.preferred == nil)
mutable.preferred = 0
check(mutable.preferred == nil)
mutable.preferred = -0.0
check(mutable.preferred == nil)
check(mutable.minimum == 30 && mutable.maximum == 144)
print("ORIGINAL_SWIFT_QUARTZCORE_CONSTRUCTOR_OPTIONAL_FLOAT_GET_SET_OK \(checks)")
print("QUARTZCORE_ORIGINAL_PROVIDER \(String(cString: path))")
