# Source runtime repairs integrated with original Unity certificate CI

The runtime used for the original macOS UnrealBuildTool build now also completes the preserved Unity/CocoaPods certificate build. Stage101 and resource configuration154 select the existing source-backed fork-queue repair, timestamp conversion, unsupported-clone fallback, quiet signal startup and genuine stat birth-time changes. These source changes and their focused controls are already published in the preceding research attachments and component forks.

The original `xcodebuild` invocation returns zero, the enclosing Darling session returns zero, and the log contains seven original `codesign` operations using the self-generated P12 fixture identity. All seven resulting products pass the original frontend's strict verification. Independent host checks verify their resource seals, code pages, CMS signatures and CodeDirectory bindings. The independent verifier's previously established negative controls were not repeated.

The existing project, CocoaPods inputs, original App and build database remain intact. This integration run uses reflink copies and reuses compilation outputs; it establishes the complete incremental build/signing invocation on the changed runtime, not a fresh C++ rebuild. The copied project and original CI arguments are retained, with the documented fixture-only certificate and provisioning settings.

`native-certificate-candidate-v11-experimental.json` records the tested inputs. `native-certificate-candidate-v12.json` adds the actual build, strict verification and independent verification evidence, allowing the normal launcher to validate this composition before adopting it. The files reference an existing local research workspace; they are not a complete cold installer recipe.

A fresh Linux Unity Editor export, CocoaPods installation and empty-DerivedData certificate build is being tested separately. This attachment does not claim Apple developer provisioning, device trust, archive/export on stage101, UE App compilation, or cold-machine reconstruction. It does not require a Mac or zsign.
