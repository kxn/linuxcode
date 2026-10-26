#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent_qos.h>
#include <stddef.h>
#include <darling/emulation/common/base.h>
#include <sys/errno.h>
#include <sys/fcntl.h>
#include <sys/time.h>
#include <mach/message.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <libsimple/lock.h>
#include <darling/emulation/xnu_syscall/bsd/impl/fcntl/fcntl.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kqueue.h>
#include <darling/emulation/xnu_syscall/bsd/impl/bsdthread/workq_kernreturn.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent64.h>

/* The implicit workqueue kqueue is shared by registration calls and a paired
 * pthread event pump. Ordinary kqueues retain their synchronous ABI.
 */
static int default_kq = -1;
static libsimple_lock_t default_lock = LIBSIMPLE_LOCK_INITIALIZER;
#define MAX_QOS_EVENTS 1024
struct qos_registration { int active; int kq; struct kevent_qos_s event; };
static struct qos_registration qos_registrations[MAX_QOS_EVENTS];
extern void* memmove(void*, const void*, __SIZE_TYPE__);
/* Paired libkqueue's default Mach receive scratch buffer is 64 bytes.
 * Limit auxiliary-buffer batches conservatively before consuming messages;
 * explicit per-registration buffers remain owned by their caller.
 */
#define BACKEND_DEFAULT_MESSAGE_CAPACITY 64
struct qos_iovec { void* base; unsigned long length; };
static int aux_copy(void* dst, const void* src, unsigned long size, int output) {
    struct qos_iovec local={output ? (void*)src : dst,size};
    struct qos_iovec remote={output ? dst : (void*)src,size};
    long pid=LINUX_SYSCALL(__NR_getpid);
    long count=LINUX_SYSCALL(output ? __NR_process_vm_writev : __NR_process_vm_readv,
            pid,&local,1,&remote,1,0);
    return count == size ? 0 : -EFAULT;
}

static int qos_record(int kq, const struct kevent_qos_s* ev) {
    int free_slot = -1;
    for (int i = 0; i < MAX_QOS_EVENTS; ++i) {
        struct qos_registration* row = &qos_registrations[i];
        if (!row->active) { if (free_slot < 0) free_slot = i; continue; }
        if (row->kq == kq && row->event.ident == ev->ident && row->event.filter == ev->filter && row->event.udata == ev->udata) {
            if (ev->flags & EV_DELETE) row->active = 0;
            else row->event = *ev;
            return 0;
        }
    }
    if (ev->flags & EV_DELETE) return 0;
    if (free_slot < 0) return -ENOSPC;
    qos_registrations[free_slot] = (struct qos_registration){1, kq, *ev};
    return 0;
}

long sys_kevent_qos(int kq, const struct kevent_qos_s* changelist, int nchanges,
        struct kevent_qos_s* eventlist, int nevents,
        void* data_out, unsigned long* data_available, unsigned int flags)
{
    const unsigned supported = KEVENT_FLAG_IMMEDIATE | KEVENT_FLAG_ERROR_EVENTS | KEVENT_FLAG_WORKQ | KEVENT_FLAG_STACK_DATA;
    int workq = !!(flags & KEVENT_FLAG_WORKQ);
    if (nchanges < 0 || nevents < 0 || nchanges > MAX_QOS_EVENTS || nevents > MAX_QOS_EVENTS)
        return -EINVAL;
    if ((nchanges && !changelist) || (nevents && !eventlist)) return -EFAULT;
    if (flags & ~supported) return -ENOTSUP;
    unsigned long residual=0, consumed=0;
    if (data_out && data_available) {
        if (aux_copy(&residual,data_available,sizeof residual,0)) return -EFAULT;
        if (nevents && residual < BACKEND_DEFAULT_MESSAGE_CAPACITY) return -ENOTSUP;
        if ((unsigned long)nevents > residual / BACKEND_DEFAULT_MESSAGE_CAPACITY)
            nevents=residual / BACKEND_DEFAULT_MESSAGE_CAPACITY;
    }
    if ((kq == -1) != workq) return -EINVAL;

    libsimple_lock_lock(&default_lock);
    if (workq && default_kq == -1) {
        int fd = sys_kqueue();
        if (fd < 0) { libsimple_lock_unlock(&default_lock); return fd; }
        int error = sys_fcntl(fd, F_SETFD, FD_CLOEXEC);
        if (error < 0) { libsimple_lock_unlock(&default_lock); return error; }
        default_kq = fd;
    }
    if (workq) kq = default_kq;
    libsimple_lock_unlock(&default_lock);

    struct kevent64_s* changes = nchanges ? __builtin_alloca(nchanges * sizeof(*changes)) : NULL;
    struct kevent64_s* events = nevents ? __builtin_alloca(nevents * sizeof(*events)) : NULL;
    for (int i = 0; i < nchanges; ++i) {
        const struct kevent_qos_s* q = &changelist[i];
        /* Extended workloop/vanished semantics must not be silently dropped. */
        if (q->xflags || q->ext[2] || q->ext[3]) return -ENOTSUP;
        changes[i] = (struct kevent64_s){ .ident=q->ident, .filter=q->filter,
            .flags=q->flags, .fflags=q->fflags, .data=q->data,
            .udata=q->udata, .ext={q->ext[0],q->ext[1]} };
    }
    /* Serialize metadata with registration, but never hold this mutex across
     * the readiness wait: the event pump must coexist with registrations.
     */
    int rv;
    if (nchanges) {
        libsimple_lock_lock(&default_lock);
        /* Reserve enough metadata capacity before changing the backend. This
         * conservative bound may reject a full-table replacement batch rather
         * than accepting events whose requested QoS would be lost.
         */
        int free_slots=0, required_slots=0;
        for (int j=0; j<MAX_QOS_EVENTS; ++j) if (!qos_registrations[j].active) ++free_slots;
        for (int i=0; i<nchanges; ++i) {
            int exists=0;
            for (int j=0; j<MAX_QOS_EVENTS; ++j) {
                struct qos_registration* row=&qos_registrations[j];
                if (row->active && row->kq == kq && row->event.ident == changelist[i].ident && row->event.filter == changelist[i].filter && row->event.udata == changelist[i].udata) { exists=1; break; }
            }
            if (!exists && !(changelist[i].flags & EV_DELETE)) ++required_slots;
        }
        if (required_slots > free_slots) { libsimple_lock_unlock(&default_lock); return -ENOSPC; }
        rv = sys_kevent64(kq, changes, nchanges, events, nevents,
                KEVENT_FLAG_ERROR_EVENTS | KEVENT_FLAG_IMMEDIATE, NULL);
        if (rv >= 0) {
            for (int i=0; i<nchanges; ++i) {
                int failed=0;
                for (int j=0; j<rv; ++j)
                    if ((events[j].flags & EV_ERROR) && events[j].data && events[j].ident == changelist[i].ident && events[j].filter == changelist[i].filter && events[j].udata == changelist[i].udata) { failed=1; break; }
                if (!failed) qos_record(kq, &changelist[i]);
            }
        }
        libsimple_lock_unlock(&default_lock);
        if (rv < 0) return rv;
    } else rv = 0;
    if (!rv && !(flags & KEVENT_FLAG_ERROR_EVENTS) && nevents) {
        struct timespec immediate = {0};
        rv = sys_kevent64(kq, NULL, 0, events, nevents, flags & KEVENT_FLAG_IMMEDIATE,
                (flags & KEVENT_FLAG_IMMEDIATE) ? &immediate : NULL);
    }
    if (rv <= 0) return rv;
    libsimple_lock_lock(&default_lock);
    for (int i=0; i<rv; ++i) {
        const struct kevent64_s* e=&events[i];
        struct kevent_qos_s q={ .ident=e->ident, .filter=e->filter,
            .flags=e->flags, .fflags=e->fflags, .data=e->data,
            .udata=e->udata, .ext={e->ext[0],e->ext[1],0,0} };
        int uses_default_buffer=1;
        for (int j=0; j<MAX_QOS_EVENTS; ++j) {
            struct qos_registration* row=&qos_registrations[j];
            if (row->active && row->kq == kq && row->event.ident == q.ident && row->event.filter == q.filter && row->event.udata == q.udata) {
                q.qos=row->event.qos;
                uses_default_buffer=!row->event.ext[1];
                if ((row->event.flags & EV_ONESHOT) && !(q.flags & EV_ERROR)) row->active=0;
                break;
            }
        }
        if (uses_default_buffer && data_out && data_available && q.filter == EVFILT_MACHPORT && q.fflags == MACH_MSG_SUCCESS && q.ext[0] && q.ext[1]) {
            unsigned long size=q.ext[1];
            if (size > BACKEND_DEFAULT_MESSAGE_CAPACITY || size > residual) {
                libsimple_lock_unlock(&default_lock); return -EOVERFLOW;
            }
            void* destination=(char*)data_out + ((flags & KEVENT_FLAG_STACK_DATA) ? residual-size : consumed);
            if (aux_copy(destination,(void*)q.ext[0],size,1)) { libsimple_lock_unlock(&default_lock); return -EFAULT; }
            q.ext[0]=(unsigned long)destination;
            consumed+=size; residual-=size;
        }
        eventlist[i]=q;
    }
    libsimple_lock_unlock(&default_lock);
    if (data_out && data_available && aux_copy(data_available,&residual,sizeof residual,1)) return -EFAULT;
    if (!workq || (flags & KEVENT_FLAG_ERROR_EVENTS)) return rv;
    struct wq_kevent_data delivery={ .events=eventlist, .nevents=rv, .capacity=nevents, .sem=0 };
    int status=sys_workq_kernreturn(WQOPS_QUEUE_REQTHREAD_FOR_KEVENT, &delivery, 1, eventlist[0].qos);
    if (status < 0) return status;
    sem_down(&delivery.sem, -1);
    return delivery.nevents;
}
