public struct Edge<T: Codable & Hashable & Sendable>: Sendable {
    public var key: T
    public var value: Double
    public init(_ key: T, _ value: Double) { self.key = key; self.value = value }
}
public func keyPath<T: Codable & Hashable & Sendable>(_: Edge<T>.Type) -> WritableKeyPath<Edge<T>, T> {
    return \Edge<T>.key
}
public func valuePath<T: Codable & Hashable & Sendable>(_: Edge<T>.Type) -> WritableKeyPath<Edge<T>, Double> {
    return \Edge<T>.value
}
