# Native Linux Unity export and imported P12 integration

## Verified imported signing identity

The original Unity/CocoaPods project builds with an RSA test identity imported through the P12 CLI. Original xcodebuild returns 0, invokes seven original CodeSign tasks, and reuses unchanged compiled objects (zero CompileC tasks). Seven products pass original strict codesign plus independent CMS, page, special-slot, and bundle-resource checks. Existing tamper controls are not repeated. Candidate v9 includes client14/daemon15, the complete 38-unit ARC source trustd and unchanged stage85. Its adoption and argument preview pass without starting native services. Older alpha11 v6 archives and dSYMs remain preserved; archive is not revalidated for changed v9.

The generated non-Apple three-level chain is correctly rejected by original Xcode with status65, rather than crashing trustd. No Apple developer provisioning or device trust is claimed. Security source: 5112cd1. The independent Developer ID optional-marker fix is published in darlingserver at 2cc033d; nine ASan/UBSan marker controls and the original Microsoft CMS/page validation pass. Experimental stage86 loads the original .NET host, but CoreCLR GC initialization still fails, so UE remains unverified.

## Fresh Editor export: prepared, currently blocked by Unity activation

Official Unity release metadata provides native Linux x86_64 Editor6000.3.27f1 (672d562a42a7) and a matching iOS Build Support module. Both archives were downloaded with resumable ranges, checked against official MD5 values, assigned local SHA256 receipts, and installed in an independent runtime prefix. The Editor has no missing linked libraries. Its actual -batchmode -nographics export invocation starts the Editor and license client, then exits with `No valid Unity Editor license found. Please activate your license.` It has not compiled the new C# exporter or produced an Xcode project yet. Raw licensing logs remain private.

The fixture contains a scene generator and a C# native call to LinuxcodePodAnswer. The export script writes a real local Pod, later integrated into UnityFramework through original Darwin CocoaPods. The end-to-end driver is prepared to run original xcodebuild through the adopted PATH wrapper on fresh DerivedData, followed by native strict and independent signature checks and verification that the actual Pod symbol is linked. These later stages remain unexecuted for the fresh fixture. No exported project is fabricated and no build success is inferred from preparation.

In a complete existing research workspace:

1. Supply an activated native Linux Unity Editor or an appropriate Unity CI license through Unity's normal activation process.
2. Run `python3 scripts/prepare-unity-editor-smoke.py` and retain the returned runtime directory.
3. Run `python3 scripts/run-unity-editor-e2e.py --prepared-run runtime/RETURNED_DIRECTORY --editor /path/to/Editor/Unity --identity-store runtime/YOUR_STORE.plist --candidate config/native-certificate-candidate-v9.json --ad-hoc-test-signing`.

The ad-hoc flag is explicit for this smoke fixture. It does not prove developer provisioning or device installation. No Mac or visible GUI is used. The installer/export drivers do not activate Unity automatically, replace user licenses, or require the user to share secrets.

Official references: https://docs.unity.com/en-us/engine/6000.3/manual/platform-specific/iphone/ios-building-and-delivering/build-process and the Unity Editor release API recorded in config/unity-editor-e2e-v1.json. Cold Linux/XIP reconstruction of the whole successful Darling environment is still a separate outstanding task.
