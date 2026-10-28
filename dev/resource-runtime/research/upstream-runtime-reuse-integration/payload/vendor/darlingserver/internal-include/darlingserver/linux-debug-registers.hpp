#ifndef DARLINGSERVER_LINUX_DEBUG_REGISTERS_HPP
#define DARLINGSERVER_LINUX_DEBUG_REGISTERS_HPP

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <initializer_list>
#include <signal.h>
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#if defined(__x86_64__)
#include <sys/user.h>
#endif

namespace DarlingServer {
// This synchronous operation never yields the server microthread while owning
// ptrace. Existing tracers are rejected; no registers are invented on failure.
inline int accessLinuxDebugRegisters(pid_t tgid, pid_t tid, uint64_t registers[8], bool write) {
#if !defined(__x86_64__)
    return ENOTSUP;
#else
    if (tgid <= 0 || tid <= 0 || !registers)
        return EINVAL;
    if (write && (registers[4] || registers[5]))
        return EINVAL; // Linux exposes DR4/DR5 as reserved and read-only.

    char path[96], status[4096];
    std::snprintf(path, sizeof(path), "/proc/%d/status", tid);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return errno == ENOENT ? ESRCH : errno;
    ssize_t size;
    do { size = read(fd, status, sizeof(status) - 1); } while (size < 0 && errno == EINTR);
    int error = size < 0 ? errno : 0;
    close(fd);
    if (error)
        return error;
    status[size] = 0;
    const char* group = std::strstr(status, "\nTgid:");
    int actualGroup = 0;
    if (!group || std::sscanf(group + 1, "Tgid: %d", &actualGroup) != 1 || actualGroup != tgid)
        return ESRCH;

    if (ptrace(PTRACE_SEIZE, tid, nullptr, nullptr) < 0)
        return errno;
    if (ptrace(PTRACE_INTERRUPT, tid, nullptr, nullptr) < 0) {
        error = errno;
        ptrace(PTRACE_DETACH, tid, nullptr, nullptr);
        return error;
    }
    int waitStatus;
    pid_t waited;
    do { waited = waitpid(tid, &waitStatus, __WALL | __WNOTHREAD); } while (waited < 0 && errno == EINTR);
    if (waited < 0) {
        error = errno;
        ptrace(PTRACE_DETACH, tid, nullptr, nullptr);
        return error;
    }
    if (!WIFSTOPPED(waitStatus))
        return ESRCH; // The task exited; the trace relationship is gone.

    // A SEIZE/INTERRUPT event is synthetic, not a SIGTRAP to deliver. Preserve
    // a real signal-delivery stop (including its siginfo) by injecting the same
    // signal when detaching. Kernel group-stop state survives DETACH unchanged.
    int resumeSignal = 0;
    if ((static_cast<unsigned>(waitStatus) >> 16) == 0) {
        siginfo_t info;
        if (ptrace(PTRACE_GETSIGINFO, tid, nullptr, &info) == 0)
            resumeSignal = WSTOPSIG(waitStatus);
        else if (errno != EINVAL)
            error = errno;
    }
    uint64_t old[8] = {};
    auto offset = [](unsigned index) { return reinterpret_cast<void*>(offsetof(struct user, u_debugreg) + index * sizeof(((struct user*)0)->u_debugreg[0])); };
    if (!error) {
        for (unsigned index = 0; index != 8; ++index) {
            errno = 0;
            long value = ptrace(PTRACE_PEEKUSER, tid, offset(index), nullptr);
            if (value == -1 && errno) { error = errno; break; }
            old[index] = static_cast<uint64_t>(value);
        }
    }
    if (!error && write) {
        auto poke = [&](unsigned index, uint64_t value) {
            return ptrace(PTRACE_POKEUSER, tid, offset(index), reinterpret_cast<void*>(static_cast<uintptr_t>(value))) < 0 ? errno : 0;
        };
        if (std::memcmp(old, registers, sizeof(old))) {
            error = poke(7, 0); // Change addresses only while breakpoints are disabled.
            for (unsigned index : {0u, 1u, 2u, 3u, 6u})
                if (!error) error = poke(index, registers[index]);
            if (!error) error = poke(7, registers[7]);
            if (error) {
                // Restore the actual snapshot if any update was rejected.
                poke(7, 0);
                for (unsigned index : {0u, 1u, 2u, 3u, 6u}) poke(index, old[index]);
                poke(7, old[7]);
            }
        }
    } else if (!error) {
        std::memcpy(registers, old, sizeof(old));
    }
    if (ptrace(PTRACE_DETACH, tid, nullptr, reinterpret_cast<void*>(static_cast<intptr_t>(resumeSignal))) < 0 && !error)
        error = errno;
    return error;
#endif
}
}
#endif
