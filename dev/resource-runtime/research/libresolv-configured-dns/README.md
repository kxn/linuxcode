# Configured DNS transport in Darling

Original macOS MSBuild reached NuGet restore and reported NU1301: `nodename nor servname provided, or not known`. A native probe reproduced it. Host DNS answered UDP, but the native resolver tried TCP port 53 and received ECONNREFUSED.

`res_vinit_from_file` enabled RES_USEVC for the initial local-server fallback before reading resolv.conf, leaving it enabled after loading an explicit server. The source change defers that automatic TCP default until no nameserver was configured. It also records a single parsed server for nondefault configuration files. Caller-supplied flags are not explicitly cleared.

All 27 configured resolver source units were rebuilt together. All 146 baseline exports are preserved, with no added exports. With the fixed library and a private read-only binding of this Linux host's resolver configuration, original native res_query, gethostbyname and getaddrinfo succeed for api.nuget.org and nuget.azure.cn. Both native and outer statuses are zero; host/backing resolver files retain their hashes. The failure and success traces are retained.

This proves the tested real DNS path. Truncation fallback, the no-configuration fallback, and preinitialized caller flags still need controlled native tests. Full UnrealBuildTool restore/build and complete certificate trust remain unverified. Current shared-memory-alias errors are independent; the source server diagnostic additions do not claim to fix them.

The fix is published under the same human Git identity in kxn/darling-libresolv, existing default main, commit 42cec61. The original pinned vendor checkout remains at cf955392e5449efb269b8b3510c755085fd36a2d with the local source edit.

Use build-libresolv-source.py with the recorded header environment, then probe-private-native-resolver.py with the recorded private stages and --libresolv-build. The resolver-stage builder reads the operator's local configuration; that host-specific snapshot is not distributed. Source, build metadata and diagnostic results are included; Apple/Unity binaries, credentials, private keys and Epic source are excluded. This is an experimental source checkpoint, not an adopted installer runtime.
