# Native local identity selection for original codesign

The original codesign command with a temporary self-signed RSA identity now passes preference lookup, selects its actual native identity using code-signing policy and private-key capabilities, and creates the native local signer. Signing is not complete: the captured next wait is SecTrustEvaluate inside PreSigningContext, which requests the paired trust daemon while constructing the certificate chain.

The opt-in version1 read-only identity file has no preference records, so SecIdentityCopyPreference validates the file and returns the real absence result. Without the environment opt-in it delegates to the original backend. SecItemCopyMatching supports unmodified code-signing/basic leaf policy and signing capability. Native certificate parsing checks dates, unknown critical extensions, key usage and required code-signing extended key usage. Other policies/query forms return errors; no chain trust, provisioning or Apple identity is synthesized.

A real native test passes23 checks using private generated identities: a positive policy-selected native identity signs and verifies RSA/SHA256, while wrong EKU, wrong key usage, expired certificates and unknown critical extensions are excluded. Unsupported/malformed policies and locked stores return errors. Keys, stores, certificates and signed products remain private and are not included here.

Early diagnostic probes forced the resource-tool framework scope onto codesign and mixed two Security object implementations. The certificate runner now uses the normal signing scope by default, matching the original build path; the coherent facade preserves the existing native signer compatibility exports. The native runtime profile resolves exact archived source inputs when a newer source revision is being developed, without changing historical binaries or expected hashes.

The current follow-up loads the paired headless trustd agent in the private session. Its first launch exposes a missing libDarlingNativeSandbox dependency; this remains a dependency/startup investigation. The published fresh Unity ad-hoc build is unchanged and remains verified separately. This checkpoint does not establish completed certificate/CMS signing, developer provisioning, device trust or a complete keychain implementation.

Source published as Comman Kang to [darling-security29c9743](https://github.com/kxn/darling-security/commit/29c9743fbd36d3696cec5970dda267b745c380cd), on the existing linuxcode/xcode-x86_64 branch.
