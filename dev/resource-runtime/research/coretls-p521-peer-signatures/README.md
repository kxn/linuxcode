# Native P-521 peer keys and real ECDSA verification

After the configured-DNS fix, original macOS dotnet aborted on a P-521 public key: the source importer expected 145 bytes, but the standard uncompressed encoding has 133. It used padded native limb storage rather than curve byte width. That calculation is corrected.

The expanded real-certificate test also exposed a short-hash overread in the scalar ECDSA path and a failing P-521 scalar verifier. The selected BoringSSL build now imports the actual public point and performs ECDSA verification through its existing implementation. Corrupted digests return failure; there are no success stubs. The scalar fallback has corrected digest sizing and mathematically corrected native-width P-521 reciprocal constants, but its full verification behavior is not established by the BoringSSL proof.

The full 56-unit source library was rebuilt by recompiling only ccec.c and preserving the other 55 verified objects and existing BoringSSL archive. It is isolated as libTLSCrypto.dylib; the modern global CoreCrypto provider is unchanged. The CoreTLS backend/front-end bytes are identical, so CF helpers can retain their existing source build against the same TLS interface.

One native run verifies real RSA, P-256, P-384 and P-521 SHA256 signatures generated independently by host OpenSSL, rejects corrupted digests, preserves peer-trust state, and rejects malformed certificate DER. Native and outer statuses are both zero. Earlier failing and timed-out runs remain failures in the attachments. Other digest/curve combinations, ECDH, full certificate trust and UnrealBuildTool completion are unverified.

Source is committed under the existing human identity on kxn/darling-corecrypto, existing linuxcode/xcode-x86_64 branch, commit 99f40f7. The old vendor HEAD and original mapped libraries were not replaced. A new original UBT run is in progress using the fixed DNS resolver and private TLS crypto v6.

Use rebuild-corecrypto-source-delta.py with the pinned 56-unit template and ccec.c as the only changed unit; stage-coretls-private-crypto.py selects it in a fresh private folder. probe-coretls-modern-peer-key.py accepts --coretls-build and --ec-curves P-256 P-384 P-521. The legacy HKDF profile now resolves its original source snapshot so this private source edit does not invalidate its unchanged baseline binary.

Private keys, Apple/Unity binaries, credentials and Epic source are excluded. This is an experimental compatibility-source checkpoint, not a new adopted signing runtime or cold-install proof.
