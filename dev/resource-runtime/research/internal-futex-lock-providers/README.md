# Real lock providers for original iOS components

Original iOS objc selected the real platform lock-with-options function but the kernel emulation library exported empty weak lock/unlock functions. Its unlock therefore did nothing and a second acquisition trapped as recursive. Native hardware watch evidence records the original binding, untouched caller and unchanged lock value.

The two empty exports are removed. Kernel workqueue and saved-file-handle state instead use the existing dependency-free libsimple Linux futex mutex. The complete 889-source kernel build intentionally removes only those two baseline exports. Both public operations now resolve to libsystem_platform. Eight native threads complete 160,000 protected increments using mixed entry points; GCD completes 9,216 tasks including idle expiry and reuse.

A fresh original IBAgent capture records the real unlock instruction and two transitions from owner to zero. Execution proceeds past objc initialization to a separate original libdispatch assertion: QoS Maintenance support required. Kernel registration still reports feature mask zero. No feature bits or locking checks were bypassed; direct event workqueue delivery needs implementation and validation. The Storyboard and complete App are not yet built.

The ibtoold snapshot was taken while the same diagnostic run was waiting for its agent; it is not an independent successful compilation. Source, text evidence and hashes only; no Apple or SDK binaries.
