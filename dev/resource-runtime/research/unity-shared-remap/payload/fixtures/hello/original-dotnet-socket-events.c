#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/event.h>
#include <sys/socket.h>
#include <unistd.h>

int main(int argc, char** argv) {
    assert(argc == 2);
    void* library = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!library) fprintf(stderr, "ORIGINAL_DOTNET_SOCKET_LOAD_ERROR %s\n", dlerror());
    assert(library);
    int32_t (*create)(intptr_t*) = dlsym(library, "SystemNative_CreateSocketEventPort");
    int32_t (*change)(intptr_t, intptr_t, int32_t, int32_t, uintptr_t) = dlsym(library, "SystemNative_TryChangeSocketEventRegistration");
    int32_t (*close_port)(intptr_t) = dlsym(library, "SystemNative_CloseSocketEventPort");
    assert(create && change && close_port);
    Dl_info owner; assert(dladdr((void*)change, &owner));
    printf("ORIGINAL_DOTNET_SOCKET_BACKEND %s\n", owner.dli_fname);
    int pair[2]; assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    assert(fcntl(pair[0], F_SETFL, O_NONBLOCK) == 0);
    intptr_t port = -1; assert(create(&port) == 0 && port >= 0);
    errno = EAGAIN; /* The same normal empty-read state as the engine's pipe. */
    int32_t status = change(port, pair[0], 0, 1, 0x1234);
    printf("ORIGINAL_DOTNET_SOCKET_REGISTRATION status=%d errno=%d\n", status, errno);
    assert(close_port(port) == 0);

    int queue = kqueue(); assert(queue >= 0);
    struct kevent event;
    EV_SET(&event, pair[0], EVFILT_READ, EV_ADD | EV_CLEAR | EV_RECEIPT, 0, 0, (void*)0x5678);
    errno = EAGAIN;
    int added = kevent(queue, &event, 1, NULL, 0, NULL);
    int saved_errno = errno;
    assert(write(pair[1], "data", 4) == 4);
    struct timespec timeout = {1, 0};
    int ready = kevent(queue, NULL, 0, &event, 1, &timeout);
    printf("DIRECT_RECEIPT_NO_OUTPUT added=%d errno=%d ready=%d flags=%x data=%ld\n",
        added, saved_errno, ready, event.flags, (long)event.data);
    int correct = status == 0 && added == 0 && ready == 1 && event.filter == EVFILT_READ
        && event.ident == (uintptr_t)pair[0] && event.udata == (void*)0x5678 && event.data >= 4;
    close(queue); close(pair[0]); close(pair[1]); dlclose(library);
    if (correct) puts("ORIGINAL_DOTNET_SOCKET_RECEIPT_AND_REAL_READINESS_OK");
    return correct ? 0 : 1;
}
