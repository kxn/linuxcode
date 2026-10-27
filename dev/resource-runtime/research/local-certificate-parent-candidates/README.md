# Local parent candidates and real certificate trust response

The paired native trustd now obtains candidate parents from the opt-in local identity file by comparing native normalized issuer and subject names. It receives actual native certificate objects, and performs its own path construction, signature checks and anchor decisions. A matching name does not confer trust. The source delegates to the original backend when no local store is selected.

The expanded native identity test passes27 checks, including matching the self-signed leaf to its actual certificate candidate. With the real paired trust service, the per-API diagnostic reports SecTrustEvaluate status0 with result5 (recoverable trust failure) and a one-certificate chain. The self-signed fixture remains untrusted; no root or provisioning status is fabricated.

The unchanged original codesign reaches a subsequent error-50. A separate CMS diagnostic reaches its actual encoding stage, whose captured stack enters the legacy CSSM/MDS module database through SecCertificateGetAlgorithmID. Certificate/CMS signing is not complete. The next experiment uses one coherent newer original Security backend; its identity and RSA checks are recorded separately and do not establish complete signing.

Stage84 clones the verified stage83 root and includes the source launchctl without changing its server/kernel/loader behavior. Its new root has not repeated the unaffected full Unity build. The successful fresh Unity ad-hoc milestone remains stage83. Source changes are published on the existing darling-security branch as Comman Kang. Private identities, certificates, stores, CMS and Apps are excluded from this checkpoint.
