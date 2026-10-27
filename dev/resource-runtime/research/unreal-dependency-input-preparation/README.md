# Prepare UE dependency inputs on Linux without substituting build output

The original macOS SDK currently fails remote NuGet TLS with OSStatus -9834. The host preparation path runs only `dotnet restore` using Microsoft's checksum-pinned Linux SDK 10.0.203 on a fresh private copy of the user's licensed Epic source. It never compiles UnrealBuildTool, transfers project.assets.json/obj/DLL outputs, disables TLS validation, or publishes Epic source.

Both the initial restore and an explicit Development restore succeeded. 71 package versions were imported as dependency inputs. Package archive bytes match NuGet's raw SHA-512 sidecars; signed-package canonical content hashes are preserved independently and checked against the final restore manifests where referenced. Complete package versions are atomically published and existing versions are never replaced. HTTP cache metadata is copied unchanged to a fresh directory. A fully seeded restore may generate no HTTP cache; the importer supports an explicit previous cache as its input and checks that input before changing destinations.

The official macOS SDK under Darling is then invoked with the original build arguments and those package/cache locations. That consumer has not completed the UBT build, so these host restore results are dependency preparation evidence only. Runtime TLS repair remains separate work.

The optional source Security services composition starts the existing source daemons with a private empty identity store while preserving the original consumer framework selection. This does not establish certificate trust or a successful TLS handshake.

An additional native DNS control verifies that explicitly preinitialized TCP flags survive reinitialization, default initialization resets flags, and one/two nameservers round-trip through public resolver APIs. Earlier actual configured DNS lookup evidence is in the separate resolver checkpoint.

All payload is source/metadata; SDKs, package archives, Epic source and Unity credentials are excluded.
