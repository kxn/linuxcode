import Foundation
let manager = FileManager.default
var checked = 0
func visit(_ path: String) throws {
    let attributes: [FileAttributeKey: Any]
    do { attributes = try manager.attributesOfItem(atPath: path) }
    catch {
        let e = error as NSError
        print("SWIFT_FILE_INFO_FAILED_PATH \(path)")
        print("SWIFT_FILE_INFO_FAILED_SCALARS \(path.unicodeScalars.map { String($0.value, radix: 16) }.joined(separator: ","))")
        print("SWIFT_FILE_INFO_ERROR \(e.domain) \(e.code) \(e.userInfo)")
        throw error
    }
    checked += 1
    if attributes[.type] as? FileAttributeType == .typeDirectory {
        for entry in try manager.contentsOfDirectory(atPath: path) {
            try visit(path + "/" + entry)
        }
    }
}
do {
    try visit(CommandLine.arguments[1])
    print("SWIFT_DIRECTORY_FILE_INFO_OK \(checked)")
} catch {
    print("SWIFT_DIRECTORY_FILE_INFO_FAILED_AFTER \(checked)")
    exit(12)
}
