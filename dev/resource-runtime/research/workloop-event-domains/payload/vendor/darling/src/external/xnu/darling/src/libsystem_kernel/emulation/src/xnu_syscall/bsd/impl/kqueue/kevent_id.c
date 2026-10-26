#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent_id.h>
#include <sys/errno.h>
#ifdef DARLING_DIRECT_KEVENT_WORKQUEUE
#include <pthread.h>
#include <libsimple/lock.h>
#include <darling/emulation/common/base.h>
#include <darling/emulation/common/simple.h>
#include <darling/emulation/linux_premigration/linux-syscalls/linux.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kqueue.h>
#include <darling/emulation/xnu_syscall/bsd/impl/kqueue/kevent_qos.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/close.h>
#include <darling/emulation/xnu_syscall/bsd/impl/bsdthread/workq_kernreturn.h>

/* Experimental userspace transport. Domains are distinct and retained until
 * process exit, with an explicit bounded pool. EVFILT_WORKLOOP ownership and
 * arbitrary workloop_ctl policy are not emulated by a successful no-op.
 */
#define DOMAIN_LIMIT 64
#define EVENT_LIMIT 16
struct workloop_domain { uint64_t id; int fd; int in_use; };
static struct workloop_domain domains[DOMAIN_LIMIT];
static libsimple_lock_t domains_lock=LIBSIMPLE_LOCK_INITIALIZER;
static long domains_process;

static void* domain_pump(void* opaque) {
    struct workloop_domain* domain=opaque;
    /* libpthread's workloop ABI reads the ID immediately before the events. */
    struct { uint64_t id; struct kevent_qos_s events[EVENT_LIMIT]; } batch;
    unsigned char receive_data[32*1024];
    int changes=0;
    for (;;) {
        batch.id=domain->id;
        unsigned long available=sizeof receive_data;
        int count=sys_kevent_qos(domain->fd,changes ? batch.events : NULL,changes,
                batch.events,EVENT_LIMIT,receive_data,&available,0);
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
    for (int i=0;i<nchanges;i++)
        if (changes[i].filter==EVFILT_WORKLOOP) return -ENOTSUP;
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
        *unused=(struct workloop_domain){.id=id,.fd=fd,.in_use=1};domain=unused;
        pthread_attr_t attr;pthread_t thread;
        int error=pthread_attr_init(&attr);
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
    return sys_kevent_qos(fd,changes,nchanges,events,nevents,data,available,
            flags&(KEVENT_FLAG_IMMEDIATE|KEVENT_FLAG_ERROR_EVENTS|KEVENT_FLAG_STACK_DATA));
#endif
}
