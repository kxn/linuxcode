# Original MSBuild Copy: report unsupported clone operations precisely

The original UBT build advanced past the repaired Touch task, then MSBuild repeatedly failed to copy three generated/native products with ENOSYS. A focused native probe established that the original .NET10 SystemNative_CopyFile entry point already copies dense, sparse and empty inputs correctly. Simple DATA/STAT/XATTR/ACL/ALL fcopyfile controls also returned zero. This was not evidence that the basic copying implementation was missing.

The actual managed File.Copy path first tries clonefile. The compatibility kernel had registered clonefileat/fclonefileat entry points but returned ENOSYS. The original .NET macOS implementation falls back to normal copying for ENOTSUP, EXDEV or EEXIST, and throws for ENOSYS. The source now explicitly reports ENOTSUP for file cloning, which this backend does not implement. It does not claim that a clone succeeded or silently replace clonefile itself with a deep copy.

An independent original MSBuild project reproduces ENOSYS before the fix. On a fresh directory after the fix, the unchanged original Copy task exits zero and the source/destination bytes match. One kernel unit was recompiled and 906 unchanged units reused. The original full UBT command is being retried in stage98; no full UBT or UE App success is claimed.

The prior full-build shutdown also exposed an interrupted internal S2C mmap request, followed by vm_remap failure. The diagnostic shows interruption, not Linux memory/map-count exhaustion. That separate issue remains unresolved; retrying an in-flight request requires correct semaphore/reply handling and has not been changed here.

References: [.NET clone fallback](https://github.com/dotnet/runtime/blob/v10.0.7/src/libraries/System.Private.CoreLib/src/System/IO/FileSystem.TryCloneFile.OSX.cs). Source repair: https://github.com/kxn/darling-xnu/commit/a2e6359 . Licensed binaries, keys and Epic source are excluded.
