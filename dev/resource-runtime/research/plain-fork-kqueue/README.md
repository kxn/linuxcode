# Plain fork: restore both kqueue backends before application callbacks

The original Intel macOS .NET process forked a child that hung before exec: standard-output redirection entered `kqueue_dup` with a mutex inherited from a different parent thread. libSystem and the direct libsystem_kernel workqueue backend have separate kqueue state; plain fork reset only one copy. The existing posix_spawn reset was insufficient for this path.

The source change exports a direct-backend child reset, weakly imports it into libSystem, and restores both copies after pthread/malloc recovery but before application child callbacks. The posix_spawn path is unchanged.

A deterministic negative control holds the actual selected kernel image's private mutex in another pthread: the old child times out inside its registered atfork callback. With the source repair, that callback redirects stdout, the child creates/closes a queue and exits zero, and the parent reads both expected bytes and still receives its original readiness event. No executable instructions are patched. Assertions are enabled.

Both fixes are published on the user's existing source fork branches. Only one kernel unit and one libSystem unit were recompiled; unchanged objects retain hash-checked provenance. Fresh staged images preserve the original bootstrap libSystem: replacing that earlier image caused a missing helper dependency and that failed result is retained.

This checkpoint proves this fork transition. The original UE consumer is being retried; it does not establish a complete UE or TLS handshake result. Apple SDK/runtime binaries, Epic source and credentials are excluded.
