#include <sys/types.h>
#include <sys/event.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>

static void fail(const char *why, int line) {
    fprintf(stderr, "PROC_FAIL line=%d %s errno=%d\n", line, why, errno);
    exit(1);
}
#define CHECK(x) do { if (!(x)) fail(#x, __LINE__); } while (0)
static const struct timespec zero = {0, 0}, deadline = {3, 0};

static pid_t child(int *gate) {
    int p[2]; CHECK(pipe(p) == 0);
    pid_t pid = fork(); CHECK(pid >= 0);
    if (pid == 0) {
        char byte;
        close(p[1]);
        if (read(p[0], &byte, 1) != 1) _exit(91);
        _exit(23);
    }
    close(p[0]); *gate = p[1]; return pid;
}
static void release(int fd) { CHECK(write(fd, "x", 1) == 1); close(fd); }
static void update(int kq, pid_t pid, unsigned flags, unsigned fflags, uintptr_t cookie) {
    struct kevent c, e;
    EV_SET(&c, pid, EVFILT_PROC, flags | EV_RECEIPT, fflags, 0, (void *)cookie);
    CHECK(kevent(kq, &c, 1, &e, 1, &zero) == 1);
    CHECK(e.filter == EVFILT_PROC && (e.flags & EV_ERROR) && e.data == 0);
}
static void event(int kq, pid_t pid, uintptr_t cookie) {
    struct kevent e;
    int n = kevent(kq, NULL, 0, &e, 1, &deadline);
    if (n != 1) fprintf(stderr, "PROC_MISSING pid=%d n=%d\n", pid, n);
    CHECK(n == 1);
    CHECK(e.filter == EVFILT_PROC && e.ident == (uintptr_t)pid);
    CHECK(e.fflags & NOTE_EXIT);
    CHECK((e.flags & (EV_EOF | EV_ONESHOT)) == (EV_EOF | EV_ONESHOT));
    CHECK(e.udata == (void *)cookie);
}

int main(void) {
    alarm(35);
    int kq = kqueue(); CHECK(kq >= 0);
    /* Baseline original process-exit transport. */
    int fd; pid_t pid = child(&fd);
    update(kq, pid, EV_ADD | EV_ENABLE, NOTE_EXIT, 1);
    release(fd); event(kq, pid, 1);
    int status; CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 23);
    fprintf(stderr, "PROC_BASELINE_EXIT_OK pid=%d\n", pid);
    for (int i = 0; i < 64; ++i) {
        pid = child(&fd);
        /* Updating flags must send NOTE_EXIT, not Linux EPOLLIN (one). */
        update(kq, pid, EV_ADD | EV_ENABLE, NOTE_EXEC, 10);
        update(kq, pid, EV_ADD | EV_ENABLE, NOTE_EXIT, 20 + i);
        /* Leave a real exit notification queued before modifying udata. */
        release(fd);
        CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status));
        usleep(2000);
        update(kq, pid, EV_ADD | EV_ENABLE, NOTE_EXIT, 100 + i);
        if (i == 0) fprintf(stderr, "PROC_QUEUED_MODIFICATION_ACK_OK pid=%d\n", pid);
        event(kq, pid, 100 + i);
        struct kevent e;
        CHECK(kevent(kq, NULL, 0, &e, 1, &zero) == 0);
    }
    /* Disabling and re-enabling must keep the same queued process event. */
    pid = child(&fd);
    update(kq, pid, EV_ADD | EV_ENABLE, NOTE_EXIT, 500);
    struct kevent c;
    EV_SET(&c, pid, EVFILT_PROC, EV_DISABLE, 0, 0, NULL);
    CHECK(kevent(kq, &c, 1, NULL, 0, &zero) == 0);
    release(fd); CHECK(waitpid(pid, &status, 0) == pid);
    struct kevent e;
    CHECK(kevent(kq, NULL, 0, &e, 1, &zero) == 0);
    EV_SET(&c, pid, EVFILT_PROC, EV_ENABLE, 0, 0, NULL);
    CHECK(kevent(kq, &c, 1, NULL, 0, &zero) == 0);
    event(kq, pid, 500);
    close(kq);
    puts("KQUEUE_PROC_REAL_EXIT_QUEUED_MODIFY_FLAGS_AND_DISABLE_ENABLE_OK iterations=64");
    return 0;
}
