# Complete UTF-8 launchd arguments and environment values

The original launchctl CF2launch_data converter uses a fixed4096-byte stack buffer and ignores failed CFStringGetCString conversion. A real private trustd job has a4142-byte DYLD_LIBRARY_PATH assignment: the old converter sends an empty argument, so env reports an empty executable name. With EnvironmentVariables, the same defect removes required library paths and trustd fails to load libDarlingNativeSandbox.

The source converter now allocates sufficient UTF-8 capacity, checks complete conversion and rejects embedded NUL characters. The complete launchctl translation unit is rebuilt; no binary instruction hook is used. A native test calls the actual static CF2launch_data function from that full source and passes39 checks, covering0/1/4094/4095/4096/4142/16384/100000-byte strings, a long multibyte string in nested ProgramArguments/EnvironmentVariables, and embedded-NUL rejection.

The rebuilt launchctl starts the real paired trustd agent. Loading both system and agent services, with diagnostic jobs running as the private session user because the test prefix lacks the dedicated _trustd account, lets the system daemon receive and process the original codesign request. Its captured stack now reaches SecPathBuilderGetNext and SecLegacyCertificateSourceCopyParents, where legacy keychain lookup still waits on SecurityServer. Certificate signing is still incomplete; no trust result or signature is synthesized.

Source is pushed as Comman Kang to the existing [Darling branch](https://github.com/kxn/darling/commit/f4de684c). The fresh Unity ad-hoc milestone is unchanged. Only source/text/metadata are included; private identity material and Apple binaries remain excluded.
