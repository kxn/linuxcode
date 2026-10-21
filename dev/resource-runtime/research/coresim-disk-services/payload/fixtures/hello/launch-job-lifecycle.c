#include <xpc/xpc.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
typedef int (*Routine)(int,xpc_object_t,xpc_object_t*);
static Routine routine;
static xpc_object_t request(void) {
 xpc_object_t r=xpc_dictionary_create(NULL,NULL,0);
 xpc_dictionary_set_uint64(r,"type",1);xpc_dictionary_set_uint64(r,"handle",0);return r;
}
static void expected(int op,xpc_object_t r,int error) {
 xpc_object_t reply=NULL;int actual=routine(op,r,&reply);
 if(actual!=error)fprintf(stderr,"op=%d expected=%d actual=%d\n",op,error,actual);
 assert(actual==error && !reply);xpc_release(r);
}
static void accept_peer(xpc_connection_t peer) {
   xpc_connection_set_event_handler(peer,^(xpc_object_t event){
    if(xpc_get_type(event)!=XPC_TYPE_DICTIONARY)return;
    xpc_object_t reply=xpc_dictionary_create_reply(event);assert(reply);
    xpc_dictionary_set_string(reply,"message","owned-job-pong");
    xpc_dictionary_set_int64(reply,"pid",getpid());
    const char*scope=getenv("DARLING_DYLD_OVERRIDE_LIBRARY_PATH");assert(scope && *scope);
    assert(getenv("DARLING_DYLD_OVERRIDE_EXECUTABLES") && getenv("DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH"));
    xpc_dictionary_set_string(reply,"scope",scope);
    xpc_connection_send_message(peer,reply);xpc_release(reply);
   });xpc_connection_resume(peer);
}
int main(int argc,char**argv) {
 if(argc==3 && !strcmp(argv[1],"--server")) {
  assert(getenv("LINUXCODE_JOB_VALUE") && !strcmp(getenv("LINUXCODE_JOB_VALUE"),"owned-value"));
  xpc_connection_t listener=xpc_connection_create_mach_service(argv[2],NULL,XPC_CONNECTION_MACH_SERVICE_LISTENER);assert(listener);
  xpc_connection_set_event_handler(listener,^(xpc_object_t peer){
   if(xpc_get_type(peer)==XPC_TYPE_CONNECTION)accept_peer((xpc_connection_t)peer);
  });xpc_connection_resume(listener);dispatch_main();
 }
 assert(argc==2);routine=(Routine)dlsym(RTLD_DEFAULT,"_launch_job_routine");assert(routine);
 char label[128];snprintf(label,sizeof(label),"org.linuxcode.job.%d",getpid());
 xpc_object_t r=request();xpc_dictionary_set_string(r,"label",label);expected(1005,r,ESRCH);
 r=request();xpc_dictionary_set_uint64(r,"type",2);expected(1011,r,ENOTSUP);
 r=request();xpc_dictionary_set_string(r,"type","wrong");expected(1011,r,EINVAL);
 r=request();xpc_dictionary_set_string(r,"plist","wrong");expected(1011,r,EINVAL);
 xpc_object_t plist=xpc_dictionary_create(NULL,NULL,0);
 xpc_dictionary_set_string(plist,"Label",label);xpc_dictionary_set_string(plist,"Program",argv[1]);
 xpc_object_t args=xpc_array_create(NULL,0);xpc_array_set_string(args,XPC_ARRAY_APPEND,argv[1]);xpc_array_set_string(args,XPC_ARRAY_APPEND,"--server");xpc_array_set_string(args,XPC_ARRAY_APPEND,label);xpc_dictionary_set_value(plist,"ProgramArguments",args);xpc_release(args);
 xpc_object_t services=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_bool(services,label,true);xpc_dictionary_set_value(plist,"MachServices",services);xpc_release(services);
 xpc_object_t environment=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_string(environment,"LINUXCODE_JOB_VALUE","owned-value");xpc_dictionary_set_value(plist,"EnvironmentVariables",environment);xpc_release(environment);
 xpc_dictionary_set_bool(plist,"OnDemand",true);
 r=request();xpc_dictionary_set_value(r,"plist",plist);xpc_dictionary_set_bool(r,"monitor",true);expected(1011,r,ENOTSUP);
 unsigned char invalid[16]={1};xpc_dictionary_set_uuid(plist,"InvalidValue",invalid);
 r=request();xpc_dictionary_set_value(r,"plist",plist);expected(1011,r,EINVAL);xpc_dictionary_set_value(plist,"InvalidValue",NULL);
 xpc_object_t nested=xpc_string_create("deep");
 for(int i=0;i<35;i++){xpc_object_t a=xpc_array_create(NULL,0);xpc_array_append_value(a,nested);xpc_release(nested);nested=a;}
 xpc_dictionary_set_value(plist,"InvalidValue",nested);xpc_release(nested);
 r=request();xpc_dictionary_set_value(r,"plist",plist);expected(1011,r,EINVAL);xpc_dictionary_set_value(plist,"InvalidValue",NULL);
 r=request();xpc_dictionary_set_value(r,"plist",plist);xpc_dictionary_set_bool(r,"monitor",false);
 xpc_object_t reply=NULL;assert(!routine(1011,r,&reply) && reply);
 xpc_object_t original_environment=xpc_dictionary_get_value(plist,"EnvironmentVariables");
 assert(!xpc_dictionary_get_value(original_environment,"DARLING_DYLD_OVERRIDE_LIBRARY_PATH"));
 const uint8_t *identifier=xpc_dictionary_get_uuid(reply,"job-handle");assert(identifier);uint8_t handle[16];memcpy(handle,identifier,16);xpc_release(reply);xpc_release(r);
 r=request();xpc_dictionary_set_value(r,"plist",plist);expected(1011,r,EEXIST);xpc_release(plist);
 r=request();xpc_dictionary_set_string(r,"label",label);reply=NULL;assert(!routine(1005,r,&reply));assert(!memcmp(handle,xpc_dictionary_get_uuid(reply,"job-handle"),16));xpc_release(reply);xpc_release(r);
 r=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_uuid(r,"job-handle",handle);reply=NULL;assert(!routine(1006,r,&reply));int64_t pid=xpc_dictionary_get_int64(reply,"pid");assert(pid>1);xpc_release(reply);xpc_release(r);
 xpc_connection_t peer=xpc_connection_create_mach_service(label,NULL,0);assert(peer);xpc_connection_set_event_handler(peer,^(xpc_object_t e){(void)e;});xpc_connection_resume(peer);
 r=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_string(r,"message","ping");dispatch_semaphore_t done=dispatch_semaphore_create(0);__block int pong=0;
 xpc_connection_send_message_with_reply(peer,r,dispatch_get_global_queue(0,0),^(xpc_object_t event){
  if(xpc_get_type(event)==XPC_TYPE_DICTIONARY){const char*message=xpc_dictionary_get_string(event,"message");pong=message && !strcmp(message,"owned-job-pong") && xpc_dictionary_get_int64(event,"pid")==pid && xpc_dictionary_get_string(event,"scope") && !strcmp(xpc_dictionary_get_string(event,"scope"),getenv("DARLING_DYLD_OVERRIDE_LIBRARY_PATH"));}
  dispatch_semaphore_signal(done);
 });assert(!dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,15*NSEC_PER_SEC)));assert(pong);xpc_release(r);xpc_connection_cancel(peer);xpc_release(peer);
 r=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_uuid(r,"job-handle",handle);reply=NULL;assert(!routine(1003,r,&reply));xpc_release(reply);xpc_release(r);
 r=request();xpc_dictionary_set_string(r,"label",label);expected(1005,r,ESRCH);
 r=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_uuid(r,"job-handle",handle);expected(1006,r,ESRCH);
 puts("LAUNCH_JOB_LIFECYCLE_NATIVE_OK submit lookup stable_uuid real_start ping_pid_match env_received scoped_loader_environment_delivered caller_plist_unchanged duplicate_rejected remove stale_handle_rejected malformed_nested_rejected");return 0;
}
