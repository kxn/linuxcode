# Real Linux memory counters through the existing Mach host interface

The original Xcode UE game build passed its original UHT invocation and planned 805 UBA actions, but never started the first compiler. The original Mac UBA memory watchdog calculates used memory from `host_statistics64`; `Scheduler::Start` waits for a nonzero initial estimate. Darling returned success with every VM counter zero, so that estimate remained zero.

The official darlinghq/darlingserver HEAD was checked against the pinned baseline (`89751e64bc6c2082f7725061824ee0e33395b0de`). Its `duct-tape/src/host.c` still contains this zero-result TODO. The surrounding XNU Mach dispatcher, rate limiter and cache already exist and are reused. No UE scheduler, UHT parser or project generator is replaced. The original tool logs and passive waiting core remain private; the core is a waiting snapshot, not evidence of a server crash.

[Source commit 214fd5d](https://github.com/kxn/darlingserver/commit/214fd5db38e283b37f98fb947fe96fe68ec11c6d) fills that existing interface from a fresh `/proc/meminfo` snapshot. `MemFree`, `Active`, `Inactive` and `Unevictable` are converted from KiB to the page units returned by `host_page_size`. Both the legacy and 64-bit interface negotiate historical revisions using the paired XNU layout. Only the returned number of integers is written. Truncated, missing or malformed measurements fail rather than succeeding with fabricated values.

Linux and Darwin do not have identical page-accounting categories. `Unevictable` covers a userspace subset of Darwin wired memory; kernel wired accounting is not claimed complete. Other Darwin-specific event, compressor, purgeable and internal/external counters remain zero. See the [Linux kernel field definitions](https://docs.kernel.org/filesystems/proc.html#meminfo). This translation supplies real observations; it does not claim full Darwin VM accounting or use `Committed_AS` as physical memory consumption.

## Verification

- The original stage103 full-count API returned four zeros, reproducing the consumer input that prevented UBA startup.
- A complete source server was rebuilt incrementally; the protected baseline build output was restored. A separate stage104 replaces only that server.
- A real Mach-O client on stage104 obtained nonzero measured values agreeing with Linux host samples. Legacy and VM64 short, historical, current and oversized buffers passed the actual Mach API checks, including untouched sentinel bytes beyond each reply.
- The current SDK declares newer VM64 fields than this Darling/XNU baseline supports. The test explicitly accepts the supported rev1 reply count; no newer-field support is fabricated.
- The original Xcode game build has been resumed on stage104 with the same workspace, scheme and failed-attempt DerivedData. Its completion, UE App signing and UE CocoaPods remain unverified in this capsule. The frozen Unity stage101 candidate is preserved.

Run `scripts/probe-host-vm-statistics.py --stage artifacts/private-procfs-auditsession103-stage.json --expect-zero-stub` for the baseline and the same script with stage104 and no baseline flag for the fix. Source files and selected reports are attached; Apple/Epic binaries, Epic sources, generated headers, original UE logs, cores and signing secrets are excluded. The existing research runtime is still required; this capsule is not a cold installer.
