#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>
#import <launch.h>
#import <xpc/xpc.h>
#include <dlfcn.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
@protocol LinuxcodeNamedPing
- (void)ping:(NSString *)value reply:(void (^)(NSString *,int))reply;
@end
@interface NamedBackend : NSObject <NSXPCListenerDelegate,LinuxcodeNamedPing>
@end
@implementation NamedBackend
- (void)ping:(NSString *)value reply:(void (^)(NSString *,int))reply {reply([@"pong:" stringByAppendingString:value],getpid());}
- (BOOL)listener:(NSXPCListener *)listener shouldAcceptNewConnection:(NSXPCConnection *)connection {
 connection.exportedInterface=[NSXPCInterface interfaceWithProtocol:@protocol(LinuxcodeNamedPing)];connection.exportedObject=self;[connection resume];return YES;
}
@end
int main(int argc,char **argv) {
 @autoreleasepool {
  if(argc==3 && !strcmp(argv[1],"--server")) {
   NamedBackend *backend=[NamedBackend new];NSXPCListener *listener=[[NSXPCListener alloc]initWithMachServiceName:[NSString stringWithUTF8String:argv[2]]];listener.delegate=backend;[listener resume];puts("NAMED_NSXPC_LISTENER_RESUMED");fflush(stdout);dispatch_main();
  }
  assert(argc==2);char label[128];snprintf(label,sizeof(label),"org.linuxcode.named-xpc.%d",getpid());
  launch_data_t job=launch_data_alloc(LAUNCH_DATA_DICTIONARY),arguments=launch_data_alloc(LAUNCH_DATA_ARRAY),services=launch_data_alloc(LAUNCH_DATA_DICTIONARY),environment=launch_data_alloc(LAUNCH_DATA_DICTIONARY),request=launch_data_alloc(LAUNCH_DATA_DICTIONARY);
  assert(job && arguments && services && environment && request);
  launch_data_dict_insert(job,launch_data_new_string(label),LAUNCH_JOBKEY_LABEL);launch_data_dict_insert(job,launch_data_new_string(argv[1]),LAUNCH_JOBKEY_PROGRAM);
  char output[1024];assert(snprintf(output,sizeof(output),"%s.server.log",argv[1])<(int)sizeof(output));
  launch_data_dict_insert(job,launch_data_new_string(output),LAUNCH_JOBKEY_STANDARDOUTPATH);launch_data_dict_insert(job,launch_data_new_string(output),LAUNCH_JOBKEY_STANDARDERRORPATH);
  const char *args[]={argv[1],"--server",label};for(unsigned i=0;i<3;++i)launch_data_array_set_index(arguments,launch_data_new_string(args[i]),i);
  launch_data_dict_insert(job,arguments,LAUNCH_JOBKEY_PROGRAMARGUMENTS);launch_data_dict_insert(services,launch_data_new_bool(1),label);launch_data_dict_insert(job,services,LAUNCH_JOBKEY_MACHSERVICES);launch_data_dict_insert(job,launch_data_new_bool(1),LAUNCH_JOBKEY_ONDEMAND);
  const char *keys[]={"DYLD_FRAMEWORK_PATH","DYLD_LIBRARY_PATH","OBJC_DISABLE_TAGGED_POINTERS"};
  for(unsigned i=0;i<3;++i){const char *v=getenv(keys[i]);if(v)launch_data_dict_insert(environment,launch_data_new_string(v),keys[i]);}
  launch_data_dict_insert(job,environment,LAUNCH_JOBKEY_ENVIRONMENTVARIABLES);launch_data_dict_insert(request,job,LAUNCH_KEY_SUBMITJOB);launch_data_t response=launch_msg(request);assert(response && launch_data_get_type(response)==LAUNCH_DATA_ERRNO && !launch_data_get_errno(response));launch_data_free(response);launch_data_free(request);
  NSXPCConnection *connection=[[NSXPCConnection alloc]initWithMachServiceName:[NSString stringWithUTF8String:label] options:0];connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(LinuxcodeNamedPing)];[connection resume];
  dispatch_semaphore_t done=dispatch_semaphore_create(0);__block int reply_pid=0;__block BOOL replied=NO;
  id<LinuxcodeNamedPing> proxy=[connection remoteObjectProxyWithErrorHandler:^(NSError *error){fprintf(stderr,"NAMED_NSXPC_ERROR domain=%s code=%ld\n",[error.domain UTF8String],(long)error.code);dispatch_semaphore_signal(done);}];
  [proxy ping:@"owned-value" reply:^(NSString *value,int pid){replied=[value isEqualToString:@"pong:owned-value"] && pid>1;reply_pid=pid;dispatch_semaphore_signal(done);}];
  long timeout=dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_SEC));assert(!timeout && replied);
  request=launch_data_alloc(LAUNCH_DATA_DICTIONARY);launch_data_dict_insert(request,launch_data_new_string(label),LAUNCH_KEY_GETJOB);response=launch_msg(request);assert(response && launch_data_get_type(response)==LAUNCH_DATA_DICTIONARY);launch_data_t pid=launch_data_dict_lookup(response,LAUNCH_JOBKEY_PID);assert(pid && launch_data_get_integer(pid)==reply_pid);launch_data_free(response);launch_data_free(request);
  puts("NAMED_NSXPC_ROUNDTRIP_AND_PID_OK");fflush(stdout);[connection invalidate];
  /* Use the already-verified job API for cleanup; legacy RemoveJob leaks an
   * internal errno after starting removal in this old launchd revision. */
  int (*routine)(int,xpc_object_t,xpc_object_t *)=dlsym(RTLD_DEFAULT,"_launch_job_routine");assert(routine);
  xpc_object_t lookup=xpc_dictionary_create(NULL,NULL,0),found=NULL;
  xpc_dictionary_set_uint64(lookup,"type",1);xpc_dictionary_set_uint64(lookup,"handle",0);xpc_dictionary_set_string(lookup,"label",label);assert(!routine(1005,lookup,&found) && found);
  const uint8_t *handle=xpc_dictionary_get_uuid(found,"job-handle");assert(handle);xpc_object_t remove=xpc_dictionary_create(NULL,NULL,0),removed=NULL;xpc_dictionary_set_uuid(remove,"job-handle",handle);assert(!routine(1003,remove,&removed));xpc_release(lookup);xpc_release(found);xpc_release(remove);if(removed)xpc_release(removed);
  puts("NAMED_NSXPC_NATIVE_OK real_launchd_job original_Foundation_listener original_Foundation_connection string_roundtrip real_pid_match");return 0;
 }
}
