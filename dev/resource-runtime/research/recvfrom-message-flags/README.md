# Correct receive-message flag translation

The stage70 full Unity/CocoaPods build advanced through SwiftPM, target dependency analysis and CreateBuildDescription, then reached original ibtool --version. A new passive stack captured CoreServices again waiting in its first process-event notification receive despite the new MSG_DONTWAIT argument. The live Linux syscall proves why: recvfrom(23, ..., 12, 0x80, ...) received the Darwin bit value, whereas Linux requires 0x40.

The existing recvfrom wrapper computed linux_flags correctly but mistakenly passed the original flags into both syscall branches. The source correction passes the already converted value in the direct syscall and socketcall forms. Only the direct x86_64 branch is natively verified here. Existing recvmsg/sendto conversions were inspected and already pass their converted flags.

An empty blocking socket pair provides an independent regression: with no O_NONBLOCK set, the old stage hangs on MSG_DONTWAIT and exits142 through a three-second alarm. The corrected stage returns EAGAIN immediately for both recv and recvfrom, verifies peek followed by consumption, and passes the existing 64 real queued process-exit/update cycles and disable/re-enable retention. The kernel delta recompiles only recvfrom.c and reuses906 original objects.

The previous full build was deliberately stopped after capturing its live wait. Its later transport disconnect, native132 and outer-9 occur during teardown and are not evidence of a separate first-fault diagnosis. The new complete incremental build uses stage71 with the same original project, CI arguments and DerivedData. No final App success is claimed. Source is pushed to the existing kxn/darling-xnu branch as Comman Kang. Only source, text and metadata are published.
