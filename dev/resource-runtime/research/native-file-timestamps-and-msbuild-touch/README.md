# File timestamp compatibility and original MSBuild Touch

The original Intel macOS UBT build compiled three real intermediate managed assemblies, then failed in Roslyn's post-compile Touch task with MSB3374 / EINVAL. A minimal original MSBuild project reproduced the same failure independently, without NuGet restore or C# compilation.

The normal nanosecond setters and the original .NET native library's UTimensat/FUTimens functions already worked. .NET's macOS FileStatus implementation may restore a file's creation time after setting access/write times earlier than birth time. The compatibility layer classified this known unimplemented operation as invalid input. It now explicitly returns ENOTSUP for inode birth/change-time setters; .NET's existing fallback handles that result. This does not simulate successful creation-time changes or claim Linux can set inode birth time.

The same focused probe exposed an independent futimes conversion bug: microseconds were passed directly to Linux utimensat as nanoseconds. The source now scales valid microseconds, rejects out-of-range values before changing either timestamp, and handles a null array as current time.

The repaired native ten-case matrix passes: path follow/nofollow, fd nanoseconds, both original .NET native entry points, omitted access time preservation, explicit unsupported birth-time result, exact futimes microseconds, invalid input preservation and null/current times. Fresh original MSBuild Touch tasks for both current time and a past date then exit zero. The old native probe and original Touch failure are retained separately. Native fixture source revisions are hash-matched to their actual reports.

Only three kernel units were recompiled, with 904 unchanged units reused. The included setattrlist helper's two direct consumers are explicitly discovered and rebuilt. The builder still does not claim complete transitive header dependency tracking.

The three intermediate Epic DLLs are inspected as managed PE/CLI images with real metadata; only their paths/hashes are published. Full UBT and UE App builds remain unverified. Original build stage97 is being retried with the unchanged command and cached dependency inputs. SDK first-run state is copied into a dedicated reusable CLI home to avoid repeating first-use setup.

References: [.NET timestamp handling](https://github.com/dotnet/runtime/blob/v10.0.7/src/libraries/System.Private.CoreLib/src/System/IO/FileStatus.Unix.cs), [macOS creation-time fallback](https://github.com/dotnet/runtime/blob/v10.0.7/src/libraries/System.Private.CoreLib/src/System/IO/FileStatus.SetTimes.OSX.cs). Source repair: https://github.com/kxn/darling-xnu/commit/a076fc1 .
