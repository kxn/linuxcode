# Modern CoreTLS peer certificate keys

The original macOS .NET restore reached a real TLS certificate callback, then waited in the legacy SecurityServer client. Loading the existing source services let it report a CSSM module error. A separate .NET executable-memory alias failure also appeared; UnrealBuildTool is not yet built.

The source CF helpers now call `SecTrustCopyKey`. The deprecated macOS `SecTrustCopyPublicKey` returns a CDSA key, whereas the helper uses modern SecKey RSA/EC accessors. The original trust object construction and peer-trust state remain intact. Malformed certificate input now returns an error rather than being treated as an absent certificate.

All three configured CF-helper source units are rebuilt together; all 19 original exports and the upward Security dependency are preserved. The native probe extracts public keys from actual RSA/P256 certificates and uses them to verify independent OpenSSL SHA256 signatures. Corrupted digests and malformed DER are rejected. Empty peer certificates retain the prior behavior. Both native and outer statuses are zero.

This verifies key extraction and real cryptographic use, not certificate trust or a completed TLS handshake. The probe uses lazy loading; eager loading still exposes an unrelated missing Rosetta dyld import. The tested source is on `kxn/darling-coretls` default `master`, commit `50f8e44`, under the existing human Git identity.

The attached service/DNS helpers are experimental diagnostics. Security services use their established normal framework scope, separate from the original .NET consumer's resource scope. The private resolver binding preserves the host and backing files, but the native getaddrinfo test failed with EAI_NONAME. Neither that test nor the failed UE attempts is reported as a successful build. The new original-consumer attempt is still in progress when this checkpoint is prepared.

Reproduction starts with `build-coretls-cfhelpers-source.py`, followed by `probe-coretls-modern-peer-key.py`, using the reports and arguments attached here. Runtime binaries, generated private keys, Unity credentials, Apple files, and Epic source are excluded. This remains a source checkpoint, not a cold-install or developer-provisioning claim.
