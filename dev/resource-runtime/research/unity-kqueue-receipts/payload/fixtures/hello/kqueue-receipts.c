#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/event.h>
#include <sys/socket.h>
#include <unistd.h>

static const struct timespec immediate = {0, 0};

int main(void) {
    alarm(10); /* A receipt must return even with spare slots and NULL timeout. */
    int pair[2];
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    assert(fcntl(pair[0], F_SETFL, O_NONBLOCK) == 0);
    int queue = kqueue();
    assert(queue >= 0);
    struct kevent changes[2], results[3];
    EV_SET(&changes[0], pair[0], EVFILT_READ, EV_ADD|EV_CLEAR|EV_RECEIPT, 0, 0, (void*)0x1234);
    EV_SET(&changes[1], pair[0], EVFILT_WRITE, EV_ADD|EV_CLEAR|EV_RECEIPT, 0, 0, (void*)0x5678);
    errno = EAGAIN;
    assert(kevent(queue, changes, 2, NULL, 0, NULL) == 0);
    assert(kevent(queue, NULL, 0, results, 3, &immediate) == 1);
    assert(results[0].filter == EVFILT_WRITE && results[0].udata == (void*)0x5678);
    EV_SET(&changes[0], pair[0], EVFILT_WRITE, EV_DISABLE|EV_RECEIPT, 0, 0, (void*)0x5678);
    assert(kevent(queue, changes, 1, results, 3, NULL) == 1);
    assert((results[0].flags & EV_ERROR) && results[0].data == 0);
    assert(results[0].ident == (uintptr_t)pair[0] && results[0].udata == (void*)0x5678);
    assert(kevent(queue, NULL, 0, results, 3, &immediate) == 0);

    /* A full receipt buffer must not prevent later changes from being applied. */
    EV_SET(&changes[0], pair[0], EVFILT_READ, EV_ADD|EV_CLEAR|EV_RECEIPT, 0, 0, (void*)0x9abc);
    EV_SET(&changes[1], pair[0], EVFILT_WRITE, EV_DELETE|EV_RECEIPT, 0, 0, NULL);
    assert(kevent(queue, changes, 2, results, 1, NULL) == 1);
    assert((results[0].flags & EV_ERROR) && results[0].data == 0);
    errno = EAGAIN;
    assert(kevent(queue, &changes[1], 1, NULL, 0, NULL) == -1 && errno == ENOENT);
    errno = EAGAIN;
    assert(kevent(queue, &changes[1], 1, results, 3, NULL) == 1);
    assert((results[0].flags & EV_ERROR) && results[0].data == ENOENT);
    EV_SET(&changes[1], pair[0], -99, EV_ADD|EV_RECEIPT, 0, 0, NULL);
    errno = EAGAIN;
    assert(kevent(queue, &changes[1], 1, NULL, 0, NULL) == -1 && errno == EINVAL);

    assert(write(pair[1], "data", 4) == 4);
    struct timespec timeout = {1, 0};
    assert(kevent(queue, NULL, 0, results, 3, &timeout) == 1);
    assert(results[0].filter == EVFILT_READ && results[0].ident == (uintptr_t)pair[0]);
    assert(!(results[0].flags & EV_ERROR) && results[0].data == 4 && results[0].udata == (void*)0x9abc);
    char buffer[4];
    assert(read(pair[0], buffer, sizeof(buffer)) == 4);
    EV_SET(&changes[0], pair[0], EVFILT_READ, EV_DELETE|EV_RECEIPT, 0, 0, NULL);
    assert(kevent(queue, changes, 1, NULL, 0, NULL) == 0);
    assert(write(pair[1], "more", 4) == 4);
    assert(kevent(queue, NULL, 0, results, 3, &immediate) == 0);

    struct kevent64_s change64 = {0}, result64[3];
    change64.ident = pair[0]; change64.filter = EVFILT_READ;
    change64.flags = EV_ADD|EV_CLEAR|EV_RECEIPT; change64.udata = 0xface;
    errno = EAGAIN;
    assert(kevent64(queue, &change64, 1, NULL, 0, 0, NULL) == 0);
    assert(kevent64(queue, NULL, 0, result64, 3, 0, &timeout) == 1);
    assert(result64[0].filter == EVFILT_READ && result64[0].data == 4 && result64[0].udata == 0xface);
    change64.flags = EV_DELETE|EV_RECEIPT;
    assert(kevent64(queue, &change64, 1, result64, 3, 0, NULL) == 1);
    assert((result64[0].flags & EV_ERROR) && result64[0].data == 0);
    close(queue); close(pair[0]); close(pair[1]);
    alarm(0);
    puts("KQUEUE_RECEIPTS_ERRORS_MULTICHANGE_AND_REAL_READINESS_OK");
    return 0;
}
