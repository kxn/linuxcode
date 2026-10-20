func exercise<T: Codable & Hashable & Sendable>(_ initial: T, _ replacement: T) {
    var edge = Edge(initial, 1.25)
    let key = keyPath(Edge<T>.self)
    let value = valuePath(Edge<T>.self)
    precondition(edge[keyPath: key] == initial)
    edge[keyPath: key] = replacement
    precondition(edge.key == replacement)
    precondition(edge[keyPath: value] == 1.25)
    edge[keyPath: value] = 9.5
    precondition(edge.value == 9.5)
}
exercise(17, 42)
exercise("before", "之后🌍")
exercise(false, true)
print("ORIGINAL_SWIFT_CODABLE_MARKER_KEYPATH_OK 12")
