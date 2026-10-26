#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent_id.h>
#include <sys/errno.h>
#ifdef DARLING_DIRECT_KEVENT_WORKQUEUE
#include <pthread.h>
#define __PTHREAD_EXPOSE_INTERNALS__ 1
#include <pthread/priority_private.h>
#include <sys/fcntl.h>
#include <libsimple/lock.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/common/simple.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kqueue.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent_qos.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent64.h>
#include <darling/emulation/xnu_syscall/bsd/impl/fcntl/fcntl.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/close.h>
#include <darling/emulation/xnu_syscall/bsd/impl/bsdthread/workq_kernreturn.h>

/* Experimental userspace transport. Domains are distinct and retained until
 * process exit, with an explicit bounded pool. Async thread requests follow
 * XNU's debounce/clear protocol. Ownership, sync waiters and workloop_ctl
 * policies are explicitly unsupported.
 */
#define DOMAIN_LIMIT 64
#define EVENT_LIMIT 16
#define CONTROL_IDENT UINT64_MAX
struct workloop_domain {
    uint64_t id;
    int fd, in_use, request_active, request_pending;
    struct kevent_qos_s request;
};
static struct workloop_domain domains[DOMAIN_LIMIT];
static libsimple_lock_t domains_lock=LIBSIMPLE_LOCK_INITIALIZER;
static long domains_process;

/* Caller holds domains_lock. An actual eventfd wakes the same domain pump
 * that handles I/O, so async requests cannot run a second concurrent servicer.
 */
static int domain_request(struct workloop_domain* domain, struct kevent_qos_s* event) {
    unsigned command=event->fflags & NOTE_WL_COMMANDS_MASK;
    if (command!=NOTE_WL_THREAD_REQUEST)
        return command==NOTE_WL_SYNC_WAIT || command==NOTE_WL_SYNC_WAKE || command==NOTE_WL_SYNC_IPC ? -ENOTSUP : -EINVAL;
    if (event->ident!=domain->id || event->xflags) return -EINVAL;
    if (event->fflags & ~(NOTE_WL_THREAD_REQUEST|NOTE_WL_UPDATE_QOS|NOTE_WL_IGNORE_ESTALE)) return -ENOTSUP;
    if (event->flags & ~(EV_ADD|EV_DELETE|EV_ENABLE|EV_DISABLE|EV_RECEIPT|EV_CLEAR)) return -ENOTSUP;
    if ((event->flags&EV_DELETE) && (event->fflags&NOTE_WL_UPDATE_QOS)) return -EINVAL;
    if (!domain->request_active && !(event->flags&EV_ADD)) return -ENOENT;
    if (!(event->flags&EV_DELETE) && (!domain->request_active || (event->fflags&NOTE_WL_UPDATE_QOS)) &&
            !_pthread_priority_thread_qos(event->qos)) return -ERANGE;
    if (event->ext[EV_EXTIDX_WL_ADDR]) {
        if(event->ext[EV_EXTIDX_WL_ADDR]&7)return -EINVAL;
        uint64_t value=0;
        struct { void* base; unsigned long length; } local={&value,sizeof value}, remote={(void*)event->ext[EV_EXTIDX_WL_ADDR],sizeof value};
        long size=LINUX_SYSCALL(__NR_process_vm_readv,LINUX_SYSCALL(__NR_getpid),&local,1,&remote,1,0);
        if (size!=sizeof value) return -EFAULT;
        uint64_t expected=event->ext[EV_EXTIDX_WL_VALUE];
        event->ext[EV_EXTIDX_WL_VALUE]=value;
        uint64_t mask=event->ext[EV_EXTIDX_WL_MASK];
        if ((value&mask)!=(expected&mask)) return event->fflags&NOTE_WL_IGNORE_ESTALE ? 0 : -ESTALE;
    }
    if (event->flags&EV_DELETE) {
        domain->request_active=domain->request_pending=0;
        return 0;
    }
    struct workloop_domain saved=*domain;
    int qos=domain->request_active && !(event->fflags&NOTE_WL_UPDATE_QOS) ? domain->request.qos : event->qos;
    unsigned disabled=domain->request_active ? domain->request.flags&EV_DISABLE : 0;
    if(event->flags&EV_DISABLE)disabled=EV_DISABLE;
    if(event->flags&EV_ENABLE)disabled=0;
    domain->request=*event;
    domain->request.qos=qos;
    domain->request.flags=EV_CLEAR|disabled;
    domain->request.ext[EV_EXTIDX_WL_LANE]=0;
    domain->request_active=1;
    domain->request_pending=!disabled;
    if (disabled) return 0;
    struct kevent64_s trigger={.ident=CONTROL_IDENT,.filter=EVFILT_USER,.fflags=NOTE_TRIGGER};
    int result=sys_kevent64(domain->fd,&trigger,1,NULL,0,KEVENT_FLAG_ERROR_EVENTS|KEVENT_FLAG_IMMEDIATE,NULL);
    if(result<0)*domain=saved;
    return result;
}

static int domain_collect(struct workloop_domain* domain, struct kevent_qos_s* events, int count) {
    int written=0;
    libsimple_lock_lock(&domains_lock);
    for(int i=0;i<count;i++) {
        if(events[i].filter==EVFILT_USER && events[i].ident==CONTROL_IDENT) {
            if(domain->request_active && domain->request_pending) {
                events[written++]=domain->request;
                domain->request_pending=0;
            }
        } else events[written++]=events[i];
    }
    libsimple_lock_unlock(&domains_lock);
    return written;
}

static void* domain_pump(void* opaque) {
    struct workloop_domain* domain=opaque;
    /* libpthread's workloop ABI reads the ID immediately before the events. */
    struct { uint64_t id; struct kevent_qos_s events[EVENT_LIMIT]; } batch;
    unsigned char receive_data[32*1024];
    int changes=0;
    for (;;) {
        batch.id=domain->id;
        unsigned long available=sizeof receive_data;
        int count=0;
        if(changes) {
            count=sys_kevent_id(domain->id,batch.events,changes,batch.events,EVENT_LIMIT,NULL,NULL,
                    KEVENT_FLAG_WORKLOOP|KEVENT_FLAG_ERROR_EVENTS|KEVENT_FLAG_IMMEDIATE);
            changes=0;
        }
        if(!count) {
            count=sys_kevent_qos(domain->fd,NULL,0,batch.events,EVENT_LIMIT,receive_data,&available,0);
            if(count>0)count=domain_collect(domain,batch.events,count);
        }
        if (count == -EINTR) continue;
        if (count < 0) { __simple_printf("Darling workloop event pump error %d\n",count); __simple_abort(); }
        if (!count) continue;
        struct wq_kevent_data delivery={.events=batch.events,.nevents=count,.capacity=EVENT_LIMIT,
            .sem=0,.workloop_id=domain->id};
        int error=sys_workq_kernreturn(WQOPS_QUEUE_REQTHREAD_FOR_WORKLOOP,&delivery,1,batch.events[0].qos);
        if (error < 0) { __simple_printf("Darling workloop worker request error %d\n",error); __simple_abort(); }
        sem_down(&delivery.sem,-1);
        changes=delivery.nevents;
        if (changes < 0) { __simple_printf("Darling workloop callback result %d\n",changes); __simple_abort(); }
    }
}
#endif

long sys_kevent_id(uint64_t id, const struct kevent_qos_s* changes, int nchanges,
        struct kevent_qos_s* events, int nevents, void* data, unsigned long* available, unsigned flags)
{
#ifndef DARLING_DIRECT_KEVENT_WORKQUEUE
    return -ENOTSUP;
#else
    const unsigned must_exist=KEVENT_FLAG_DYNAMIC_KQ_MUST_EXIST;
    const unsigned must_not_exist=KEVENT_FLAG_DYNAMIC_KQ_MUST_NOT_EXIST;
    const unsigned allowed=KEVENT_FLAG_WORKLOOP|KEVENT_FLAG_IMMEDIATE|KEVENT_FLAG_ERROR_EVENTS|
        KEVENT_FLAG_STACK_DATA|must_exist|must_not_exist;
    if (!id || id==UINT64_MAX || !(flags&KEVENT_FLAG_WORKLOOP) ||
            ((flags&must_exist)&&(flags&must_not_exist))) return -EINVAL;
    if (flags&~allowed) return -ENOTSUP;
    if (nchanges<0 || nevents<0 || nchanges>1024 || nevents>1024) return -EINVAL;
    if ((nchanges&&!changes) || (nevents&&!events)) return -EFAULT;
    /* Only the currently servicing callback may poll this domain directly. */
    if (nevents && !(flags&KEVENT_FLAG_ERROR_EVENTS) && workq_current_workloop_id()!=id) return -EXDEV;
    if (!workq_workloop_callback_registered()) return -ENOTSUP;
    long pid=LINUX_SYSCALL(__NR_getpid);
    libsimple_lock_lock(&domains_lock);
    if (domains_process && domains_process!=pid) { libsimple_lock_unlock(&domains_lock); return -ENOTSUP; }
    domains_process=pid;
    struct workloop_domain *domain=NULL,*unused=NULL;
    for (int i=0;i<DOMAIN_LIMIT;i++) {
        if (!domains[i].in_use) { if(!unused)unused=&domains[i]; }
        else if(domains[i].id==id) domain=&domains[i];
    }
    if (domain && (flags&must_not_exist)) { libsimple_lock_unlock(&domains_lock); return -EEXIST; }
    if (!domain && (flags&must_exist)) { libsimple_lock_unlock(&domains_lock); return -ENOENT; }
    if (!domain) {
        if (!unused) { libsimple_lock_unlock(&domains_lock); return -ENOSPC; }
        int fd=sys_kqueue();
        if (fd<0) { libsimple_lock_unlock(&domains_lock); return fd; }
        int error=sys_fcntl(fd,F_SETFD,FD_CLOEXEC);
        struct kevent64_s control={.ident=CONTROL_IDENT,.filter=EVFILT_USER,.flags=EV_ADD|EV_CLEAR};
        if(!error)error=sys_kevent64(fd,&control,1,NULL,0,KEVENT_FLAG_ERROR_EVENTS|KEVENT_FLAG_IMMEDIATE,NULL);
        if(error<0) {sys_close(fd);libsimple_lock_unlock(&domains_lock);return error;}
        *unused=(struct workloop_domain){.id=id,.fd=fd,.in_use=1};domain=unused;
        pthread_attr_t attr;pthread_t thread;
        error=pthread_attr_init(&attr);
        if(!error) {
            error=pthread_attr_setdetachstate(&attr,PTHREAD_CREATE_DETACHED);
            if(!error)error=pthread_attr_setstacksize(&attr,512*1024);
            if(!error)error=pthread_create(&thread,&attr,domain_pump,domain);
            pthread_attr_destroy(&attr);
        }
        if(error) { domain->in_use=0;sys_close(fd);libsimple_lock_unlock(&domains_lock);return -error; }
    }
    int fd=domain->fd;
    libsimple_lock_unlock(&domains_lock);
    /* Snapshot before writing receipts: libdispatch aliases input and output. */
    struct kevent_qos_s* input=nchanges ? __builtin_alloca(nchanges*sizeof(*input)) : NULL;
    for(int i=0;i<nchanges;i++)input[i]=changes[i];
    int count=0;
    for(int i=0;i<nchanges;i++) {
        struct kevent_qos_s event=input[i];
        int error=0;
        if(event.filter==EVFILT_WORKLOOP) {
            libsimple_lock_lock(&domains_lock);
            error=domain_request(domain,&event);
            libsimple_lock_unlock(&domains_lock);
            if(error || (event.flags&EV_RECEIPT)) {
                if(count<nevents) {event.flags|=EV_ERROR;event.data=-error;events[count++]=event;}
                else if(error)return error;
            }
        } else {
            if(event.filter==EVFILT_USER && event.ident==CONTROL_IDENT) return -EINVAL;
            int result=sys_kevent_qos(fd,&event,1,events ? events+count : NULL,nevents-count,NULL,NULL,
                    KEVENT_FLAG_ERROR_EVENTS|KEVENT_FLAG_IMMEDIATE);
            if(result<0)return result;
            count+=result;
        }
    }
    if(count || (flags&KEVENT_FLAG_ERROR_EVENTS) || !nevents)return count;
    count=sys_kevent_qos(fd,NULL,0,events,nevents,data,available,
            flags&(KEVENT_FLAG_IMMEDIATE|KEVENT_FLAG_STACK_DATA));
    return count>0 ? domain_collect(domain,events,count) : count;
#endif
}
