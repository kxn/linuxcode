public protocol HasValue {
    associatedtype Value
    var value: Value { get }
}
public func valuePath<T: HasValue & Sendable>(_: T.Type) -> KeyPath<T, T.Value> {
    return \T.value
}
public struct Box<T> { public var value: T }
public func nestedPath<T: HasValue & Sendable>(_: T.Type) -> KeyPath<Box<T>, T.Value> {
    return \Box<T>.value.value
}
public func sendableOnlyPath<T: Sendable>(_: T.Type) -> KeyPath<Box<T>, T> {
    return \Box<T>.value
}
