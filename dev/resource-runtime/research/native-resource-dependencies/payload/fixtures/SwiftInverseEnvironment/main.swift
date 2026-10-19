struct NoncopyableBuffer: ~Copyable, BufferRepresentable {
    var buffer: Int
}
struct CopyableBuffer: BufferRepresentable {
    var buffer: String
}
let integers = NoncopyableBuffer.bufferIdentity
let strings = CopyableBuffer.bufferIdentity
for value in [0, -17, 42] {
    precondition(value[keyPath: integers] == value)
}
for value in ["", "Darling", "原版 Swift"] {
    precondition(value[keyPath: strings] == value)
}
print("ORIGINAL_SWIFT_INVERSE_ENVIRONMENT_KEYPATH_PROJECTIONS_OK 6")
