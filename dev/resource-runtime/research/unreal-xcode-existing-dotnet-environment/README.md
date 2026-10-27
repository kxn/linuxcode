# Reuse the standalone UBT environment in the Xcode build

The original Xcode workspace reached its external build target and invoked Epic's unmodified XcodeBuild.sh and BuildUBT.sh. The first attempt failed before C++ compilation: .NET first-use NuGet migration could not stat `/tmp/.dotnet`; original Xcode returned status 75 after the external target failed.

The standalone UBT path already has a working private temporary filesystem launcher and a persistent CLI home/NuGet cache. The Xcode diagnostic driver now accepts the existing temporary-stage selector. Its existing prebuild-command mechanism sources the same .NET environment before starting original Xcode, so child UE tools inherit it. Existing configd/DiskArbitration preparation is reused. There is no new mutex implementation or change to the UE build scripts.

The integrated attempt has progressed into the original MSBuild worker processes. This checkpoint records a live observation, not build success. The earlier failed attempt's DerivedData is reused; no fresh-build claim is made for this retry. Complete UE C++ compilation, App signing and CocoaPods integration for UE remain unverified. Unity's frozen stage101/candidate12 is unchanged.

A separate read-only observation confirms that the StorageKit library mentioned in background CoreDeviceService failures already exists in the MDNS framework stage with matching hashes. The failing service's library scope is an integration issue; no new StorageKit implementation was added. Its complete service operation has not been verified. Private Apple/Epic binaries, cores, identities and raw original tool logs are excluded.
