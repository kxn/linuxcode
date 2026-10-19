public protocol BufferRepresentable: ~Copyable {
    associatedtype Buffer
    var buffer: Buffer { get }
}

extension BufferRepresentable where Self: ~Copyable {
    @inline(never)
    public static var bufferIdentity: KeyPath<Buffer, Buffer> {
        \Buffer.self
    }
}
