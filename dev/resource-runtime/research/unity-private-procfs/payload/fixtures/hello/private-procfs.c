#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/event.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/wait.h>
#include <unistd.h>

#define INTERNAL_PROC "/private/var/db/darling/proc"
extern char** environ;
static const char payload[] = "private procfs data";

int main(int argc, char** argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 2 && !strcmp(argv[1], "--child")) {
        errno = 0;
        assert(fcntl(100, F_GETFD) == -1 && errno == EBADF);
        char buffer[sizeof(payload)] = {0};
        assert(read(201, buffer, sizeof(buffer)) == sizeof(payload));
        assert(!memcmp(buffer, payload, sizeof(payload)));
        puts("PRIVATE_PROCFS_CLOEXEC_DEFAULT_AND_DUP_ACTION_OK");
        return 0;
    }
    assert(argc == 1);
    struct stat st;
    errno = 0; assert(stat("/proc", &st) == -1 && errno == ENOENT);
    assert(stat(INTERNAL_PROC, &st) == 0 && S_ISDIR(st.st_mode));
    assert(stat("/Volumes/SystemRoot/proc", &st) == 0 && S_ISDIR(st.st_mode));
    int info = open(INTERNAL_PROC "/self/stat", O_RDONLY); assert(info >= 0);
    char buffer[4096] = {0};
    assert(read(info, buffer, sizeof(buffer)-1) > 0); close(info);
    assert(atoi(buffer) == getpid());
    printf("PRIVATE_PROCFS_SELF_PID %d\n", getpid());
    info = open(INTERNAL_PROC "/self/mountinfo", O_RDONLY); assert(info >= 0);
    assert(read(info, buffer, sizeof(buffer)) > 0); close(info);
    unsigned cpus = 0; size_t bytes = sizeof(cpus);
    assert(sysctlbyname("hw.ncpu", &cpus, &bytes, NULL, 0) == 0 && bytes == sizeof(cpus) && cpus > 0);
    info = open(INTERNAL_PROC "/cpuinfo", O_RDONLY); assert(info >= 0);
    memset(buffer, 0, sizeof(buffer));
    assert(read(info, buffer, sizeof(buffer)-1) > 0); close(info);
    char* cores_line = strstr(buffer, "cpu cores"); assert(cores_line);
    char* separator = strchr(cores_line, ':'); assert(separator);
    unsigned expected_cores = atoi(separator+1); assert(expected_cores > 0);
    unsigned cores = 0; bytes = sizeof(cores);
    assert(sysctlbyname("machdep.cpu.core_count", &cores, &bytes, NULL, 0) == 0 && cores == expected_cores);
    printf("PRIVATE_PROCFS_SYSCTL cpus=%u cores=%u actual_proc_cores=%u\n", cpus, cores, expected_cores);
    struct kinfo_proc process; bytes = sizeof(process);
    int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()};
    assert(sysctl(mib, 4, &process, &bytes, NULL, 0) == 0 && bytes == sizeof(process));
    assert(process.kp_proc.p_pid == getpid());

    char name[] = "/tmp/linuxcode-private-proc-XXXXXX";
    int file = mkstemp(name); assert(file >= 0);
    assert(write(file, payload, sizeof(payload)) == sizeof(payload));
    char alias[128]; snprintf(alias, sizeof(alias), INTERNAL_PROC "/self/fd/%d", file);
    int duplicate = open(alias, O_RDONLY); assert(duplicate >= 0);
    struct stat original, other;
    assert(fstat(file, &original) == 0 && fstat(duplicate, &other) == 0);
    assert(original.st_dev == other.st_dev && original.st_ino == other.st_ino);
    memset(buffer, 0, sizeof(buffer));
    assert(read(duplicate, buffer, sizeof(payload)) == sizeof(payload) && !memcmp(buffer, payload, sizeof(payload)));
    close(duplicate);
    snprintf(alias, sizeof(alias), "/dev/fd/%d", file);
    duplicate = open(alias, O_RDONLY); assert(duplicate >= 0); close(duplicate);

    int queue = kqueue(); assert(queue >= 0);
    struct kevent event;
    EV_SET(&event, file, EVFILT_VNODE, EV_ADD|EV_CLEAR|EV_RECEIPT, NOTE_WRITE, 0, (void*)0x1234);
    int registered = kevent(queue, &event, 1, NULL, 0, NULL);
    if (registered != 0) fprintf(stderr, "VNODE_REGISTRATION result=%d errno=%d %s\n", registered, errno, strerror(errno));
    assert(registered == 0);
    assert(write(file, "!", 1) == 1);
    struct timespec timeout = {2, 0};
    assert(kevent(queue, NULL, 0, &event, 1, &timeout) == 1);
    assert(event.filter == EVFILT_VNODE && event.ident == (uintptr_t)file && event.udata == (void*)0x1234);
    assert(!(event.flags & EV_ERROR) && (event.fflags & NOTE_WRITE));
    close(queue);

    int pipes[2]; assert(pipe(pipes) == 0);
    assert(write(pipes[1], payload, sizeof(payload)) == sizeof(payload));
    snprintf(alias, sizeof(alias), INTERNAL_PROC "/self/fd/%d", pipes[0]);
    duplicate = open(alias, O_RDONLY|O_NONBLOCK); assert(duplicate >= 0);
    assert(read(duplicate, buffer, sizeof(payload)) == sizeof(payload) && !memcmp(buffer, payload, sizeof(payload)));
    close(duplicate); close(pipes[0]); close(pipes[1]);

    assert(lseek(file, 0, SEEK_SET) == 0);
    assert(dup2(file, 100) == 100);
    posix_spawnattr_t attributes; posix_spawn_file_actions_t actions;
    assert(posix_spawnattr_init(&attributes) == 0);
    assert(posix_spawnattr_setflags(&attributes, POSIX_SPAWN_CLOEXEC_DEFAULT) == 0);
    assert(posix_spawn_file_actions_init(&actions) == 0);
    assert(posix_spawn_file_actions_adddup2(&actions, file, 201) == 0);
    char* arguments[] = {argv[0], "--child", NULL};
    pid_t child = -1;
    assert(posix_spawn(&child, argv[0], &actions, &attributes, arguments, environ) == 0);
    int status = -1;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    posix_spawn_file_actions_destroy(&actions); posix_spawnattr_destroy(&attributes);
    close(100); close(file); unlink(name);
    puts("PRIVATE_PROCFS_LAYOUT_REAL_PROCESS_SYSCTL_FD_PIPE_VNODE_AND_SPAWN_OK");
    return 0;
}
