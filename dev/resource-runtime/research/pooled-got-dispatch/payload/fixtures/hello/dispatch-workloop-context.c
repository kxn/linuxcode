#include <dispatch/dispatch.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
extern dispatch_workloop_t dispatch_workloop_copy_current(void);
extern _Bool dispatch_workloop_is_current(dispatch_workloop_t);
static atomic_int active, errors, completed;
static void context(dispatch_workloop_t expected) {
    dispatch_workloop_t actual=dispatch_workloop_copy_current();
    if(actual!=expected || (expected && !dispatch_workloop_is_current(expected))) atomic_fetch_add(&errors,1);
    if(actual) dispatch_release(actual);
}
int main(void) {
    setbuf(stdout,NULL);
    puts("WORKLOOP_REAL_TARGET_QUEUE_TEST_BEGIN");
    dispatch_workloop_t loop=dispatch_workloop_create("test.fallback.workloop");
    dispatch_queue_t middle=dispatch_queue_create("test.middle",NULL);
    dispatch_queue_t a=dispatch_queue_create("test.a",NULL),b=dispatch_queue_create("test.b",NULL);
    dispatch_group_t group=dispatch_group_create();
    dispatch_set_target_queue(middle,(dispatch_queue_t)loop);
    dispatch_set_target_queue(a,middle);dispatch_set_target_queue(b,(dispatch_queue_t)loop);
    dispatch_suspend(middle);dispatch_suspend(b);
    int sequence_storage[2]={0,0};int *sequence=sequence_storage;
    for(int i=0;i<512;i++) for(int lane=0;lane<2;lane++) {
        dispatch_queue_t target=lane?b:a;
        dispatch_group_async(group,target,^{
            if(atomic_fetch_add(&active,1)!=0 || sequence[lane]++!=i) atomic_fetch_add(&errors,1);
            context(loop);atomic_fetch_add(&completed,1);atomic_fetch_sub(&active,1);
        });
    }
    dispatch_resume(middle);dispatch_resume(b);
    if(dispatch_group_wait(group,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC))) return 81;
    printf("WORKLOOP_REAL_ASYNC_FIFO_SERIALIZATION completed=%d errors=%d\n",atomic_load(&completed),atomic_load(&errors));
    if(atomic_load(&errors) || atomic_load(&completed)!=1024) return 82;
    for(int i=0;i<128;i++) {
        /* The SPI explicitly says dispatch_sync does not adopt the target
           workloop; async_and_wait does adopt it. */
        dispatch_sync(a,^{context(NULL);});
        if(dispatch_workloop_copy_current()!=NULL || dispatch_workloop_is_current(loop)) return 83;
    }
    dispatch_workloop_t other=dispatch_workloop_create("test.other.workloop");
    dispatch_queue_t c=dispatch_queue_create("test.c",NULL);dispatch_set_target_queue(c,(dispatch_queue_t)other);
    for(int i=0;i<64;i++) dispatch_group_async(group,a,^{
        context(loop);
        dispatch_sync(c,^{context(loop);});
        dispatch_async_and_wait(c,^{context(other);});
        context(loop);
    });
    if(dispatch_group_wait(group,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC))) return 84;
    for(int i=0;i<64;i++) dispatch_group_async(group,dispatch_get_global_queue(0,0),^{
        dispatch_workloop_t current=dispatch_workloop_copy_current();
        if(current || dispatch_workloop_is_current(loop) || dispatch_workloop_is_current(other)) atomic_fetch_add(&errors,1);
        if(current) dispatch_release(current);
    });
    if(dispatch_group_wait(group,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC)) || atomic_load(&errors)) return 85;
    dispatch_release(c);dispatch_release(other);dispatch_release(a);dispatch_release(b);dispatch_release(middle);dispatch_release(loop);dispatch_release(group);
    puts("WORKLOOP_REAL_NESTED_TARGET_FIFO_SYNC_RESTORE_AND_INDEPENDENT_ROOT_CONTEXT_OK");
    return 0;
}
