# Original codesign creates and verifies a real certificate-signed iOS App

The unchanged original Intel codesign binary now signs the actual iOSCocoaPodsSmoke iPhoneOS/arm64 App using a temporary self-generated RSA code-signing certificate. Original codesign --verify --strict returns0, reports valid on disk and satisfies its Designated Requirement. No zsign is used. The original codesign copy is byte-identical to the pinned recovery reference.

Independent verification checks18 SHA256 code pages, three special slots and two resource entries. The CodeDirectory has no ad-hoc bit. OpenSSL verifies the actual1789-byte CMS against that exact CodeDirectory and only the supplied fixture certificate. Modified CodeDirectory, code page, Info.plist and CodeResources cases are rejected. The independent path currently rejects alternate CodeDirectories rather than leaving them unchecked.

The missing upstream requirement parser is built from34 source units into csparser.bundle. The framework now has the correct bundle metadata, plugin layout and original module-description resources. Client and paired daemon processes retain separate coherent scopes. This preserves the real parser and certificate checks; a self-signed fixture is not classified as an Apple developer identity or made trusted.

The working candidate uses the source159-unit headless SecurityServer, paired trustd, stage84 loader/kernel/server root, source launchctl, the read-only local identity store, original native CMS, and the real requirement compiler. Earlier CMS/module and parser failures remain in separate checkpoints. Linux host permissions and namespace behavior are unchanged; this does not implement macOS named Sandbox enforcement.

In an existing research workspace, one command selects the exact pinned candidate and creates a new private test identity:

```sh
python3 scripts/probe-original-codesign-certificate.py --candidate config/native-certificate-candidate-v1.json
```

This is an existing-workspace verification command, not a clean-machine installer. The newly certificate-signed product is the small CocoaPods smoke App; Unity's previously published full fresh build remains ad-hoc. Developer certificates, provisioning, device execution, full Unity certificate CI, UE and complete Linux/XIP reconstruction remain unverified. Public artifacts contain source, text and hashes only, without keys, identity files, certificates, CMS or signed Apps.
