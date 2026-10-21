#include <xpc/xpc.h>
#include <mach/mach.h>
#include <dlfcn.h>
#include <errno.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
typedef int (*Routine)(int,xpc_object_t,xpc_object_t*);
typedef int (*Async)(int,xpc_object_t,mach_port_t);
typedef int (*Receive)(mach_port_t,xpc_object_t*,uint64_t);
typedef void (*Audit)(xpc_object_t,audit_token_t*);
int main(void) {
    const char* (*describe)(int)=dlsym(RTLD_DEFAULT,"xpc_strerror");
    assert(describe);
    int errors[]={0,EINVAL,ENOTSUP,ENOENT,-1,INT_MAX,107,165};
    for (unsigned i=0;i<sizeof(errors)/sizeof(*errors);++i) {
        const char* message=describe(errors[i]);
        assert(message && *message);
        if (errors[i]<107 || errors[i]>165) assert(!strcmp(message,strerror(errors[i])));
    }
    puts("XPC_STRERROR_NATIVE_OK errno_and_unknown_nonnull extended_descriptions_generic");
    Routine job=(Routine)dlsym(RTLD_DEFAULT,"_launch_job_routine");
    Routine domain=(Routine)dlsym(RTLD_DEFAULT,"_xpc_domain_routine");
    Async asynchronous=(Async)dlsym(RTLD_DEFAULT,"_launch_job_routine_async");
    Receive receive=(Receive)dlsym(RTLD_DEFAULT,"xpc_pipe_receive");
    Audit audit=(Audit)dlsym(RTLD_DEFAULT,"xpc_dictionary_get_audit_token");
    assert(job && domain && asynchronous && receive && audit);
    Routine routines[]={domain,job};uint64_t subsystems[]={3,10};
    for (unsigned i=0;i<2;++i) {
        xpc_object_t request=xpc_dictionary_create(NULL,NULL,0),reply=NULL;
        assert(routines[i](0x7fffffff,request,&reply)==ENOTSUP && !reply);
        assert(xpc_dictionary_get_uint64(request,"subsystem")==subsystems[i]);
        assert(xpc_dictionary_get_uint64(request,"routine")==0x7fffffff);
        xpc_release(request);
    }
    mach_port_t port=MACH_PORT_NULL;
    assert(!mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&port));
    xpc_object_t request=xpc_dictionary_create(NULL,NULL,0),reply=NULL;
    assert(!asynchronous(0x7fffffff,request,port));
    assert(xpc_dictionary_get_uint64(request,"subsystem")==10);
    assert(!receive(port,&reply,0) && reply);
    assert(xpc_dictionary_get_int64(reply,"error")==ENOTSUP);
    audit_token_t token={0};audit(reply,&token);
    assert(token.val[5]==1 && token.val[1]==0);
    xpc_release(request);xpc_release(reply);
    assert(!mach_port_destroy(mach_task_self(),port));
    request=xpc_string_create("invalid-request");reply=NULL;
    assert(job(1,request,&reply)==EINVAL && !reply);
    assert(domain(1,request,&reply)==EINVAL && !reply);
    assert(asynchronous(1,request,MACH_PORT_NULL)==EINVAL);
    xpc_release(request);
    puts("LAUNCH_JOB_ROUTINES_NATIVE_OK sync_domain=3 sync_job=10 async_reply=launchd unsupported_operations_rejected");
    return 0;
}
