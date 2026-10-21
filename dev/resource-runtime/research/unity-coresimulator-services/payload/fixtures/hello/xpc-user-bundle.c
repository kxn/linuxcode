#include <xpc/xpc.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef void (*Add)(const char*,unsigned);
typedef char* (*Metadata)(const char*);
static void accept_peer(xpc_connection_t peer) {
        xpc_connection_set_event_handler(peer, ^(xpc_object_t event) {
            if (xpc_get_type(event)!=XPC_TYPE_DICTIONARY) return;
            const char* value=xpc_dictionary_get_string(event,"ping");
            assert(value && !strcmp(value,"actual-on-demand-job"));
            xpc_object_t reply=xpc_dictionary_create_reply(event);assert(reply);
            xpc_dictionary_set_string(reply,"pong",value);
            xpc_dictionary_set_int64(reply,"pid",getpid());
            xpc_connection_send_message(peer,reply);xpc_release(reply);
        });
        xpc_connection_resume(peer);
}
static void server(void) {
    const char* value=getenv("LINUXCODE_XPC_FIXTURE_VALUE");
    assert(value && !strcmp(value,"value-from-bundle-info"));
    assert(getenv("DARLING_DYLD_OVERRIDE_EXECUTABLES"));
    assert(getenv("DARLING_DYLD_OVERRIDE_LIBRARY_PATH"));
    assert(getenv("DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH"));
    xpc_main(accept_peer);
    abort();
}
int main(int argc,char** argv) {
    if (strstr(argv[0],"/FixtureService")) server();
    assert(argc==4);
    const char* name="org.linuxcode.user-bundle-fixture";
    Add add=(Add)dlsym(RTLD_DEFAULT,"xpc_add_bundle");
    Metadata version=(Metadata)dlsym(RTLD_DEFAULT,"launch_version_for_user_service_4coresim");
    Metadata path=(Metadata)dlsym(RTLD_DEFAULT,"launch_path_for_user_service_4coresim");
    assert(add && version && path);
    if (!strcmp(argv[1],"register") || !strcmp(argv[1],"auto")) {
        char* absent=version(name);assert(!absent);
        if (!strcmp(argv[1],"auto")) {
            char image[4096];snprintf(image,sizeof(image),"%s/Fixture",argv[2]);
            void* loaded=dlopen(image,RTLD_NOW|RTLD_LOCAL);
            if (!loaded) fprintf(stderr,"FRAMEWORK_LOAD_ERROR %s\n",dlerror());
            assert(loaded);
            void (*initialize)(void)=dlsym(RTLD_DEFAULT,"xpc_init_services");assert(initialize);
            initialize();
        } else { errno=0;add(argv[2],0);assert(!errno); }
        errno=0;add(argv[2],0);assert(!errno);
        errno=0;add(argv[2],1);assert(errno==ENOTSUP);
        errno=0;add("relative.xpc",0);assert(errno==EINVAL);
    }
    char* v=version(name);char* p=path(name);
    fprintf(stderr,"USER_BUNDLE_METADATA version=%s path=%s errno=%d\n",v?v:"NULL",p?p:"NULL",errno);
    assert(v && !strcmp(v,"7.3"));assert(p && !strcmp(p,argv[3]));free(v);free(p);
    if (!strcmp(argv[1],"query")) { puts("USER_BUNDLE_CROSS_PROCESS_METADATA_OK");return 0; }
    dispatch_queue_t queue=dispatch_queue_create("fixture.client",NULL);
    dispatch_semaphore_t done=dispatch_semaphore_create(0);
    xpc_connection_t connection=xpc_connection_create_mach_service(name,queue,0);assert(connection);
    xpc_connection_set_event_handler(connection,^(xpc_object_t event) {(void)event;});
    xpc_connection_resume(connection);
    xpc_object_t request=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_string(request,"ping","actual-on-demand-job");
    __block int success=0;
    xpc_connection_send_message_with_reply(connection,request,queue,^(xpc_object_t reply) {
        const char* value=xpc_get_type(reply)==XPC_TYPE_DICTIONARY?xpc_dictionary_get_string(reply,"pong"):NULL;
        success=value && !strcmp(value,"actual-on-demand-job") && xpc_dictionary_get_int64(reply,"pid")>0;
        dispatch_semaphore_signal(done);
    });
    assert(!dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,15*NSEC_PER_SEC)));
    assert(success);xpc_release(request);xpc_connection_cancel(connection);xpc_release(connection);
    puts("USER_BUNDLE_REAL_ON_DEMAND_XPC_REPLY_OK");return 0;
}
