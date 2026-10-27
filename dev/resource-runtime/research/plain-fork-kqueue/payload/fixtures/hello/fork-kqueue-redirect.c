#include <assert.h>
#include <dlfcn.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/event.h>
#include <sys/wait.h>
#include <unistd.h>

static pthread_mutex_t *backend_lock;
static atomic_int held, release_lock;
static int output_pipe[2];

static void *hold_backend_lock(void *unused) {
    (void)unused;
    assert(pthread_mutex_lock(backend_lock) == 0);
    atomic_store_explicit(&held, 1, memory_order_release);
    while (!atomic_load_explicit(&release_lock, memory_order_acquire)) usleep(1000);
    assert(pthread_mutex_unlock(backend_lock) == 0);
    return NULL;
}

static void application_child_handler(void) {
    alarm(3);
    if (dup2(output_pipe[1], STDOUT_FILENO) != STDOUT_FILENO) _exit(91);
    if (write(STDOUT_FILENO, "H", 1) != 1) _exit(92);
}

int main(int argc, char **argv) {
    assert(argc == 3); setbuf(stdout, NULL); alarm(20);
    int negative = strcmp(argv[2], "negative") == 0;
    void *kernel = dlopen("/usr/lib/system/libsystem_kernel.dylib", RTLD_LAZY | RTLD_LOCAL);
    assert(kernel);
    void *duplicate = dlsym(kernel, "kqueue_dup"); assert(duplicate);
    Dl_info owner; assert(dladdr(duplicate, &owner));
    assert(strstr(owner.dli_fname, "libsystem_kernel.dylib"));
    backend_lock = (pthread_mutex_t *)((uintptr_t)owner.dli_fbase + strtoull(argv[1], NULL, 16));
    int (*create)(void) = dlsym(kernel, "kqueue_impl"); assert(create);
    int queue = create(); assert(queue >= 0);
    int watched[2]; assert(pipe(watched) == 0 && pipe(output_pipe) == 0);
    struct kevent event;
    EV_SET(&event, watched[0], EVFILT_READ, EV_ADD, 0, 0, (void *)0x815);
    assert(kevent(queue, &event, 1, NULL, 0, NULL) == 0);
    assert(pthread_atfork(NULL, NULL, application_child_handler) == 0);
    pthread_t worker; assert(pthread_create(&worker, NULL, hold_backend_lock, NULL) == 0);
    while (!atomic_load_explicit(&held, memory_order_acquire)) usleep(1000);
    puts("FORK_KQUEUE_OTHER_THREAD_OWNS_REAL_BACKEND_MUTEX");
    pid_t child = fork(); assert(child >= 0);
    if (child == 0) {
        close(output_pipe[0]); close(output_pipe[1]);
        int fresh = create(); if (fresh < 0) _exit(93); close(fresh);
        if (write(STDOUT_FILENO, "C", 1) != 1) _exit(94);
        _exit(0);
    }
    atomic_store_explicit(&release_lock, 1, memory_order_release);
    assert(pthread_join(worker, NULL) == 0);
    close(output_pipe[1]);
    char observed[2]; size_t bytes = 0; ssize_t count;
    while (bytes < sizeof(observed) && (count = read(output_pipe[0], observed + bytes, sizeof(observed) - bytes)) > 0) bytes += count;
    int status; assert(waitpid(child, &status, 0) == child);
    printf("FORK_KQUEUE_CHILD_STATUS %d bytes=%zu\n", status, bytes);
    if (negative) assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGALRM && bytes == 0);
    else assert(WIFEXITED(status) && WEXITSTATUS(status) == 0 && bytes == 2 && memcmp(observed, "HC", 2) == 0);
    assert(write(watched[1], "P", 1) == 1);
    struct timespec timeout = {1, 0};
    int ready = kevent(queue, NULL, 0, &event, 1, &timeout);
    printf("FORK_KQUEUE_PARENT_READINESS %d\n", ready);
    assert(ready == 1 && event.ident == (uintptr_t)watched[0] && event.filter == EVFILT_READ && event.data >= 1);
    close(output_pipe[0]); close(watched[0]); close(watched[1]); close(queue);
    puts(negative ? "FORK_KQUEUE_OLD_MUTEX_DEADLOCK_REPRODUCED" :
         "FORK_KQUEUE_CHILD_USER_HANDLER_REDIRECT_NEW_QUEUE_AND_PARENT_READINESS_OK");
    return 0;
}
