# P12 import and native public certificate chains

The Linux installer now accepts a caller RSA PKCS#12 bundle through `import-identity`. The password comes from a named environment variable. The private read-only store is created atomically with mode 600 and is never overwritten. Extra public certificates remain certificate candidates, not signing identities or trusted roots.

Five host tests cover real RSA signing with the imported key, exact chain preservation, file permissions, wrong passwords, unsupported EC keys, and preservation of existing files. The native fixture passes 32 checks with paired client v14 and daemon v15 scopes: one identity, three certificates, leaf policy filtering, parent lookup, successful chain evaluation under an explicit test root and rejection under a different key with the same root subject. No system trust store changes are made.

Original codesign signs and strictly verifies a sample iOS application using the imported identity. Independent verification confirms its CMS contains the exact three imported certificates, and OpenSSL verifies the chain with only the explicit fixture root. This is a generated test chain; Apple developer provisioning and device installation are not established.

The first full Unity integration attempt with experimental candidate v7 timed out in GatherProvisioningInputs (outer -9, no original returned status). Its diagnostic attempt is tracked separately. Candidate v7 has no successful full-build receipt and must not be advertised as an adoptable replacement for verified v6. Previously verified alpha11 Unity archives remain preserved.

Security source commit: `19e1da5` in kxn/darling-security, branch linuxcode/xcode-x86_64. No private key, P12, identity-store contents, Apple binary or licensed UE source is included here. The generator allows developers to create their own private test fixture.

Run host tests from the integration repository with LINUXCODE_P12_FIXTURE_GENERATOR pointing to the payload scripts/prepare-p12-chain-fixture.py, using `python3 -m unittest discover -s tests -p test_identity_import.py`.
