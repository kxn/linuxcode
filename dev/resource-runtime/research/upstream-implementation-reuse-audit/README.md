# Reuse existing upstream implementations

Before adding a compatibility implementation, identify the library actually selected by the failing process. Check the pinned upstream source, build target, exported symbols and dependency wiring. If the implementation already exists, correct its integration. Change the corresponding component only after identifying an interface gap or a concrete defect; preserve a baseline and an actual consumer check.

This is a targeted review of existing source and evidence, not a completed audit of all historical compatibility patches.

The pinned CoreTLS source already lists the complete `system_coretls` implementation. Its separate `libcoretls` facade uses `dummy.c`; examining that facade alone would give a misleading impression that the implementation is absent. The pinned LibSystem build reexports both `system_coretls` and `system_copyfile`. The existing TLS work builds those upstream sources and adapts their dependencies and ABI; it does not establish complete TLS/trust compatibility.

The original .NET 10 file-copy control demonstrates working upstream `fcopyfile` for the tested data, sparse-file and simple metadata cases. The subsequent fix changes unsupported clone syscall results from ENOSYS to ENOTSUP so the original caller can use that existing copy implementation. It adds no replacement clone or copy engine, and the controls do not establish full ACL or metadata conformance. See the [copy fallback evidence](../original-msbuild-copy-fallback/README.md).

Other confirmed changes repair existing upstream implementations: `futimes` passed microseconds to a nanosecond interface, and the stat conversion left output fields uninitialized. Their [timestamp](../native-file-timestamps-and-msbuild-touch/README.md) and [birth-time](../unreal-real-birthtime-ios-validation/README.md) records contain the actual consumer checks and limitations. The paired fork-queue changes also address requirements introduced by this experimental environment's second queue backend; they must not be described as a universally missing upstream component.

The attached audit records the exact pinned commits and source hashes. Source presence alone does not prove that a selected runtime library exports or correctly executes an API. Future failures must continue to distinguish absent implementation, interface differences, existing implementation defects, and errors introduced by our build or runtime composition.
