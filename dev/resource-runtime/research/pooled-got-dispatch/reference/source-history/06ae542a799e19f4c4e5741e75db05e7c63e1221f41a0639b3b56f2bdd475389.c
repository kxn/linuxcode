#include "internal.h"
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    setbuf(stdout, NULL);
    dispatch_source_type_t type = dlsym(RTLD_DEFAULT, "_dispatch_source_type_exclaves_notification");
    if (argc == 2 && !strcmp(argv[1], "missing")) {
        if (type) return 61;
        puts("DISPATCH_EXCLAVES_TYPE_ABSENT_CONTROL_OK");
        return 0;
    }
    if (!type || strcmp(type->dst_kind, "exclaves_notification") ||
        type->dst_filter != -18 || type->dst_action != DISPATCH_UNOTE_ACTION_SOURCE_OR_FFLAGS ||
        type->dst_flags != (DISPATCH_EV_DIRECT|EV_CLEAR) || type->dst_fflags ||
        type->dst_mask != UINT32_MAX || type->dst_size != sizeof(struct dispatch_source_refs_s) ||
        !type->dst_create || !type->dst_merge_evt) return 62;
    printf("DISPATCH_EXCLAVES_LAYOUT filter=%d action=%u flags=%u fflags=%u mask=%u size=%u\n",
        type->dst_filter, type->dst_action, type->dst_flags, type->dst_fflags, type->dst_mask, type->dst_size);
    Dl_info owner;
    if (!dladdr(type, &owner) || !owner.dli_fname) return 63;
    printf("DISPATCH_EXCLAVES_OWNER %s\n", owner.dli_fname);
    if (!dladdr(type->dst_create, &owner) || !owner.dli_fname) return 64;
    printf("DISPATCH_EXCLAVES_CREATE_OWNER %s\n", owner.dli_fname);
    if (!dladdr(type->dst_merge_evt, &owner) || !owner.dli_fname) return 65;
    printf("DISPATCH_EXCLAVES_MERGE_OWNER %s\n", owner.dli_fname);
    if (dispatch_source_create(type, 0, 1, NULL) || dispatch_source_create(type, 1, 0, NULL)) return 66;
    unsigned char saved[sizeof(*type)];
    memcpy(saved, type, sizeof(saved));
    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
    dispatch_source_t source = dispatch_source_create(type, 1, 1, dispatch_get_global_queue(0, 0));
    if (!source) return 67;
    dispatch_source_set_cancel_handler(source, ^{ dispatch_semaphore_signal(semaphore); });
    // Cancel before activation: this tests allocation and cancellation without
    // asking an unsupported kernel backend to deliver exclaves notifications.
    dispatch_source_cancel(source);
    dispatch_resume(source);
    if (dispatch_semaphore_wait(semaphore, dispatch_time(DISPATCH_TIME_NOW, 5*NSEC_PER_SEC))) return 68;
    dispatch_release(source);
    dispatch_async(dispatch_get_global_queue(0, 0), ^{ dispatch_semaphore_signal(semaphore); });
    if (dispatch_semaphore_wait(semaphore, dispatch_time(DISPATCH_TIME_NOW, 5*NSEC_PER_SEC))) return 69;
    dispatch_release(semaphore);
    if (memcmp(saved, type, sizeof(saved))) return 70;
    int queue = kqueue();
    if (queue < 0) return 71;
    struct kevent64_s change = { .ident=1, .filter=-18, .flags=EV_ADD|EV_RECEIPT, .fflags=1 };
    struct kevent64_s receipt = {0};
    struct timespec zero = {0};
    errno = 0;
    int count = kevent64(queue, &change, 1, &receipt, 1, KEVENT_FLAG_IMMEDIATE, &zero);
    int error = count < 0 ? errno : (count == 1 && (receipt.flags & EV_ERROR) ? (int)receipt.data : 0);
    close(queue);
    if (error != EINVAL && error != ENOSYS) return 72;
    printf("DISPATCH_EXCLAVES_UNSUPPORTED_FILTER error=%d\n", error);
    puts("DISPATCH_EXCLAVES_TYPE_LAYOUT_CALLBACKS_CANCEL_AND_ASYNC_OK");
    return 0;
}
