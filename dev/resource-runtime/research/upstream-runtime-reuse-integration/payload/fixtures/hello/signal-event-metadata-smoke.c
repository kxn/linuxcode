/* Owned recoverable signal event: no invalid memory access, child crash,
 * external process inspection or alternate exception/unwind implementation. */
#include <errno.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

static volatile sig_atomic_t caught, caught_signal;
static void handler(int number) { caught_signal = number; ++caught; }
static unsigned checks;
static int check(int condition, const char* name) {
    if (!condition) {
        printf("SIGNAL_EVENT_METADATA_FAIL check=%s errno=%d\n", name, errno);
        return 0;
    }
    ++checks; printf("SIGNAL_EVENT_METADATA_CHECK %s\n", name); return 1;
}
int main(void) {
    setbuf(stdout, NULL);
    char executable[1024]; uint32_t capacity = sizeof(executable);
    if (!check(_NSGetExecutablePath(executable, &capacity) == 0, "own-executable-path")) return 1;
    printf("SIGNAL_EVENT_METADATA_BEGIN getpid=%ld signal=%d expected_executable=%s recoverable=1\n",
        (long)getpid(), SIGSEGV, executable);
    struct sigaction action = {0}, previous = {0}, current = {0};
    action.sa_handler = handler; action.sa_flags = SA_RESTART;
    sigemptyset(&action.sa_mask);
    if (!check(sigaction(SIGSEGV, &action, &previous) == 0, "install-handler")) return 1;
    sigset_t unblock, previous_mask; sigemptyset(&unblock); sigaddset(&unblock, SIGSEGV);
    if (!check(sigprocmask(SIG_UNBLOCK, &unblock, &previous_mask) == 0, "unblock-own-signal")) return 1;
    int status = raise(SIGSEGV);
    if (!check(status == 0, "raise-returned")) return 1;
    if (!check(caught == 1 && caught_signal == SIGSEGV, "handler-caught-once")) return 1;
    if (!check(sigaction(SIGSEGV, NULL, &current) == 0 && current.sa_handler == handler, "handler-remains-installed")) return 1;
    if (!check(sigaction(SIGSEGV, &previous, NULL) == 0, "restore-handler")) return 1;
    if (!check(sigprocmask(SIG_SETMASK, &previous_mask, NULL) == 0, "restore-mask")) return 1;
    printf("SIGNAL_EVENT_METADATA_PASS checks=%u caught=%d signal=%d normal_exit=0\n",
        checks, (int)caught, (int)caught_signal);
    return 0;
}
