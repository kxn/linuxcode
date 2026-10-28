# Original Xcode compiles the CocoaPod inside the UE workspace

The original Xcode workspace build on stage106 created `Intermediate/LinuxcodePods/Development-iphoneos/libLocalMath.a`. Its modification time is after that attempt started. Independent LLVM inspection finds two Mach-O arm64 object members and the defined `_local_add` symbol. The archive is 7,136 bytes; the selected report records its SHA256. The original UE legacy target depends on this actual Pod target and its authored ModuleRules names this same archive; final UBT link consumption is still pending.

This proves actual CocoaPods source compilation and archiving, beyond the earlier installation/configuration checks. It does not prove an engine executable or App. The native server subsequently segfaulted in `dtape_semaphore_up`; Xcode then observed refused semaphore RPCs and exited 132. The caller that supplied the null semaphore is not yet known. A new attempt reuses the existing Pod/cache and has passive server fault capture armed to obtain that caller. No runtime or engine source is changed for that diagnostic repeat.

Only selected metadata, archive headers and symbols are attached. The archive, original tools, original UE logs and private runtime are excluded. UE App compilation, Pod linkage in that executable and final signing remain unverified. The original Unity milestone remains preserved.
