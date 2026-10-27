# Headless trustd ARC object lifetimes

A full Unity build using a three-level imported signing chain stopped in GatherProvisioningInputs. A live stack showed original DVT waiting for SecTrustEvaluateWithError. A minimal reproducer using the same Apple External Developer plus revocation (0x23) policies caught a real trustd SIGSEGV in objc_msgSend called by TrustURLSessionCache sessionForAuditToken: during revocation fetching.

The static libtrustd target omitted OBJC_ARC, while the separate trustd executable target enabled ARC. Its synthesized session-map setter consequently performed a bare pointer assignment. The source fix adds OBJC_ARC to libtrustd. This preserves the original validation and revocation logic.

The separate builder compiles all 31 daemon/library units plus seven required utility units, using ARC for Objective-C files. It reuses only identical compilation dependencies. Supplemental header categories declare APIs missing from Darling headers; they provide no runtime implementations. New source trustd and its exact private backend are selected only through experimental candidate v8, for both system and agent jobs. Verified v6 remains available.

The fixed minimal native test returns an actual rejection (accepted=0, error=-67880) for the generated non-Apple test chain with outer status 0. It does not crash or accept the synthetic identity as an Apple developer identity. The earlier Basic/codeSigning unanchored control also returns rejection. System trust stores are unchanged. Full Unity integration with v8 is recorded separately when it finishes.

Security fix is published at 5112cd1 in kxn/darling-security, branch linuxcode/xcode-x86_64. UE bootstrap observations are separate: the original Intel .NET host starts, but a Microsoft certificate with an additional critical Apple .18 marker requires a narrow embedded-signature compatibility update. UE build success is not established. Licensed engine source and Apple binaries remain local.
