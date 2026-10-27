# Fresh Unity project: original Release archive and verified dSYMs

The same v12/stage101/config154 runtime that completed the fresh Linux Unity certificate build now also completes original `xcodebuild archive` in Release configuration. The project and successful Debug DerivedData are copied with reflinks and mounted privately at their original guest paths. The native archive command and enclosing Darling invocation both return zero. The four protected Debug App/build-database/project guards remain unchanged.

The original archive run executes 48 CompileC tasks and five codesign operations. Its xcarchive contains the actual iPhoneOS arm64 App and embedded UnityFramework. Both archived products pass original strict verification and independent CMS, page and resource checks using the same self-generated P12 certificate.

Both required standalone symbol files contain real DWARF4 data and match their archived executable UUIDs. The App's debug-info section contains 2,305 bytes; UnityFramework's contains 30,679,942 bytes. The upstream native LLVM19 `llvm-dwarfdump --verify` completes successfully on each entire dSYM file. The independent archive inspector also checks Mach-O file type, architecture, archive metadata, section bounds and UUID matching. No replacement DWARF implementation was added.

The reusable preparation helper now accepts the fresh Editor end-to-end evidence as well as the older certificate-CI fixture. The milestone recorder accepts the normal CLI's status/plan evidence and derives product coverage from the actual archive, rather than assuming the older fixture's seven products. Every archived App/framework requires native and independent checks. Release records require actual standalone-symbol verification.

The immutable v12 candidate file describes archive as pending at the time of its creation. This later attachment verifies archive on those same unchanged inputs; the candidate file is not rewritten. Earlier v6 archive evidence remains separate.

Raw compiler output, generated Apps/dSYMs, SDKs and private signing material remain private. The attached task transcript retains selected verbatim task/status lines and the raw log SHA256. This milestone uses fixture-only certificate/provisioning settings. Apple developer provisioning, device installation, export, the UE App and complete cold reconstruction remain unverified.
