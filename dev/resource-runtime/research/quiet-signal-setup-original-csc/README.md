# Keep normal signal setup quiet for original compiler tasks

The original UE build now compiles/copies nine shared assemblies. One Csc task was nevertheless marked as an error solely because normal Darling signal setup unconditionally printed `darling_sigexc_self()` into the child process diagnostic stream.

A minimal original macOS MSBuild Csc task, forced to use an out-of-process original compiler, reproduced that exact error while still producing a valid 3,072-byte managed DLL. Removing the single unconditional startup print makes the same original task succeed on a fresh fixture directory and produce the managed Smoke/get_Answer assembly. Signal registration, delivery, exception handling and genuine failure diagnostics are unchanged in the source diff. No compiler diagnostics are filtered by the harness.

Only one kernel unit was recompiled and 906 unchanged units reused. Full original UBT is being retried in stage99; a complete UBT or UE App is not claimed here. The intermittent interrupted S2C mmap observed on earlier shutdowns remains separate unresolved work.

Source: https://github.com/kxn/darling-xnu/commit/1d0e340 . Apple/Epic binaries are excluded; the C# smoke source and MSBuild fixture are included.
