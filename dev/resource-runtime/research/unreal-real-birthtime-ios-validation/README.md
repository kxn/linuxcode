# Genuine file birth times and original UBT iOS platform validation

After the complete original macOS UBT build and successful tool startup, ValidatePlatforms exposed an out-of-range creation timestamp containing a pointer-sized value. The legacy Linux-to-Darwin stat converters never initialized the birth-time field. A native control prefilled output buffers with 0xa5 and demonstrated that all seven successful stat-family calls retained the poison in that field.

The source initializes the complete stat outputs and obtains genuine birth times through Linux statx for path, fd and lstat calls. Unsupported/unavailable birth time remains initialized zero. No invented timestamp or successful creation-time setter is used. The extra birth-time query does not establish an atomic snapshot against concurrent path replacement.

The first candidate matched six controls but missed the separate lstat path; that failed report is retained. The final seven cases exactly match independent host statx seconds/nanoseconds, including files, directories, symlink follow/nofollow, relative directory-fd lookup and an opened-then-unlinked file. The symlink and target are created at distinguishable real times so following the wrong object cannot pass the final test.

The original UBT next identified missing official SDK JSON inputs in the sparse private checkout. Eight absent configurations were restored byte-for-byte from the pinned Epic Git commit; existing files were not replaced and their contents are excluded here. With the final stat source, the original unchanged ValidatePlatforms command explicitly reports `##PlatformValidate: IOS VALID 26.1.1` and exits zero. This output uses UBT's reported main-version string, not an independent inventory of every installed SDK component.

This verifies metadata reading and the original tool's iOS platform check. It does not establish UE Xcode project generation, native UnrealHeaderTool C++ compilation, a complete UE iOS App, provisioning or trusted IPA export. The already successful full UBT C# build was not repeated for this metadata-only repair.

Source: https://github.com/kxn/darling-xnu/commit/237a5e5 . All Apple/Epic binary inputs and Epic configuration contents remain private.
