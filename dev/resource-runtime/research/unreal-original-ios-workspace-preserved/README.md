# Original UBT preserves the iOS workspace

Using the original generator's default platform selection resolves the workspace cleanup collision observed with explicit `-Platforms=IOS`. With the official `-NoIntelliSense` option, the original Intel macOS UBT finishes under Darling with native and outer status zero. The iOS workspace remains on disk; its XML parses and all four referenced pbxproj files exist. The game shared scheme refers to the LinuxcodeUESmoke target.

The engine and workspace writer were not modified. The attached command changes only the generator options. Other default Apple workspaces may also be emitted; the active build target is iOS. This checkpoint does not establish complete IDE index preparation, UE App compilation, game execution, CocoaPods integration for UE or signing. The actual original Xcode game build follows separately.

Generated projects and original Epic logs/binaries remain private. Evidence includes source/server identities, native result, workspace/project/scheme hashes, and the exact original generator arguments.
