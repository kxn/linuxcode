struct Concrete: HasValue, Sendable { var value: Int }
let sample = Concrete(value: 42)
let direct = valuePath(Concrete.self)
let nested = nestedPath(Concrete.self)
precondition(sample[keyPath: direct] == 42)
precondition(Box(value: sample)[keyPath: nested] == 42)
let markerOnly = sendableOnlyPath(Int.self)
precondition(Box(value: 42)[keyPath: markerOnly] == 42)
print("ORIGINAL_SWIFT_MARKER_KEYPATH_RUNTIME_OK 3")
