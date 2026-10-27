# Original UBT published to its standard UE directory

After the original macOS SDK compiled UnrealBuildTool and its twelve shared project assemblies, the standard `Engine/Binaries/DotNET/UnrealBuildTool` directory was still absent. The original UE build scripts expect that directory.

The original macOS dotnet now completes the upstream `publish --no-build` step under Darling, with both native and outer status zero. All thirteen published project assemblies exactly match the already verified original macOS compiler outputs. This reuses those outputs and does not repeat their C# compilation or the unchanged Help test.

The attached arguments follow the publish step in the pinned official UE BuildUBT script. Epic source and binaries remain private. Complete official Mac/iOS dependency input preparation and original project generation continue separately; this checkpoint does not claim a complete UE App build.
