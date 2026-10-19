import Distributed

distributed actor Echo<Element: Codable & Sendable> {
    typealias ActorSystem = LocalTestingDistributedActorSystem
    distributed func echo(_ value: Element) -> Element { value }
}

@main struct AccessibleFunctionsSmoke {
    static func main() async throws {
        let system = LocalTestingDistributedActorSystem()
        let integers = Echo<Int>(actorSystem: system)
        let strings = Echo<String>(actorSystem: system)
        let integer = try await integers.echo(-73)
        let string = try await strings.echo("原版 accessible function")
        precondition(integer == -73)
        precondition(string == "原版 accessible function")
        print("ORIGINAL_ACCESSIBLE_FUNCTION_LOCAL_CALLS_OK 2")
    }
}
