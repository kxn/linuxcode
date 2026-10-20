public struct MarkerOuter<T: Sendable> {
    public struct Pair<U: Sendable> {
        public var first: T
        public var second: U
        public init(_ first: T, _ second: U) {
            self.first = first
            self.second = second
        }
        public static func path() -> KeyPath<Self, U> {
            return \Self.second
        }
    }
}
