#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d %s\n", __LINE__, #x); return 1; } } while (0)
struct functions {
    int version;
    int (*create)(pthread_t *, void *, const pthread_attr_t *, void *(*)(void *), void *);
};
static void (*install)(const struct functions *);
static int (*create_in_group)(pthread_t *, void *, const pthread_attr_t *, void *(*)(void *), void *);
static void *group_expected, *argument_expected;
static const pthread_attr_t *attributes_expected;
static unsigned calls, mismatches;
static int fail_creation;
static void *routine(void *arg) { return (void *)((uintptr_t)arg + 17); }
static int provider(pthread_t *thread, void *group, const pthread_attr_t *attr,
                    void *(*start)(void *), void *arg) {
    ++calls;
    if (group != group_expected || attr != attributes_expected ||
        arg != argument_expected || start != routine) ++mismatches;
    if (fail_creation) return EAGAIN;
    return pthread_create(thread, attr, start, arg);
}
static int expect_crash(int duplicate, const struct functions *f) {
    pid_t pid = fork();
    if (pid < 0) return 0;
    if (pid == 0) {
        alarm(10);
        if (duplicate) install(f);
        else { pthread_t t; create_in_group(&t, (void *)0x1234, NULL, routine, NULL); }
        _exit(91);
    }
    int status;
    if (waitpid(pid, &status, 0) != pid) return 0;
    return WIFSIGNALED(status) &&
        (WTERMSIG(status) == SIGILL || WTERMSIG(status) == SIGTRAP || WTERMSIG(status) == SIGABRT);
}
int main(void) {
    setbuf(stdout, NULL);
    void *h = dlopen("/usr/lib/system/libsystem_pthread.dylib", RTLD_LAZY | RTLD_LOCAL);
    CHECK(h);
    install = dlsym(h, "pthread_install_workgroup_functions_np");
    create_in_group = dlsym(h, "pthread_create_with_workgroup_np");
    int (*allow_signals)(int) = dlsym(h, "_pthread_workqueue_allow_send_signals");
    CHECK(install && create_in_group && allow_signals);
    errno = 0; CHECK(allow_signals(SIGUSR1) == -1 && errno == ENOTSUP);
    struct functions f = { 1, provider };
    CHECK(expect_crash(0, &f));
    install(&f);
    CHECK(expect_crash(1, &f));
    pthread_attr_t attributes;
    CHECK(pthread_attr_init(&attributes) == 0);
    attributes_expected = &attributes; group_expected = (void *)0x123456789aull;
    argument_expected = (void *)0x100000083ull;
    pthread_t t; void *result;
    CHECK(create_in_group(&t, group_expected, &attributes, routine, argument_expected) == 0);
    CHECK(pthread_join(t, &result) == 0 && result == (void *)((uintptr_t)argument_expected + 17));
    fail_creation = 1;
    CHECK(create_in_group(&t, group_expected, &attributes, routine, argument_expected) == EAGAIN);
    CHECK(calls == 2 && mismatches == 0);
    CHECK(pthread_attr_destroy(&attributes) == 0);
    puts("PTHREAD_WORKGROUP_PROVIDER_FORWARDING_REAL_THREAD_AND_FAILURE_CONTRACT_OK");
    return 0;
}
