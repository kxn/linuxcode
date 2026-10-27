# Original macOS UBT: dependency restore and precise mapping diagnostics

After the paired plain-fork repair, the unchanged original Intel macOS SDK build command started eight MSBuild workers and restored all 13 UE projects under Darling. The run then failed because Epic's `Library.props` dependency input had not been downloaded. During shutdown, a genuine RW/RX alias creation failed at shared remap's `source-backing-map` phase and the original runtime aborted. The run is explicitly unsuccessful; no UBT DLL or UE App is claimed.

The missing official inputs are fetched from the user's local Commit.gitdeps.xml. The source helper downloads only selected packs concurrently, verifies decompressed pack sizes/SHA1 and each selected file's size/SHA1 against the official manifest, and refuses to replace different existing files. It uses no copied Epic source in this repository. The first invocation restored the missing Horde proto inputs, Intel macOS Oodle library, UBA metadata/binaries and UBT ignore file. Library.props was separately restored from its manifest entry with identical verification.

A source diagnostic change retains mapping behavior and adds failure-phase messages plus returned client mmap errno. The new server was built by recompiling one C++ unit; the earlier memory diagnostic unit was reused. The baseline build output was restored and only a fresh runtime stage selects the diagnostic server. The current complete-input original build is a separate run.

Passive thread samples taken during dependency restore were transient: the process subsequently continued. They are not treated as proof of a new deadlock. The full TLS handshake and original UBT build remain unverified. The successful restore uses cached dependency inputs prepared separately on Linux; no host-compiled UBT outputs are used.

Source diagnostics: https://github.com/kxn/darlingserver/commit/cfdd501 . Apple/Epic binaries and source inputs are excluded from this checkpoint.
