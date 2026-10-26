#import <Foundation/Foundation.h>
#import <objc/message.h>
#include <xpc/xpc.h>
#include <xpc/connection.h>
#include <dispatch/dispatch.h>
#include <mach/mach.h>
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <stdbool.h>
static bool (*expects_reply)(xpc_object_t);
int main(void) {
 @autoreleasepool {
  expects_reply=(bool(*)(xpc_object_t))dlsym(RTLD_DEFAULT,"xpc_dictionary_expects_reply");if(!expects_reply)return 10;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,8*NSEC_PER_SEC),dispatch_get_global_queue(0,0),^{fputs("REPLY_CAPABILITY_TIMEOUT\n",stderr);exit(9);});
  xpc_connection_t listener=xpc_connection_create(NULL,NULL);
  xpc_connection_set_event_handler(listener,^(xpc_object_t peer){
   if(xpc_get_type(peer)!=XPC_TYPE_CONNECTION)return;
   xpc_connection_set_event_handler(peer,^(xpc_object_t request){
    if(xpc_get_type(request)!=XPC_TYPE_DICTIONARY)return;
    BOOL expects=expects_reply(request);mach_port_t port=((mach_port_t(*)(id,SEL))objc_msgSend)((id)request,sel_registerName("incomingPort"));mach_port_type_t type=0;mach_port_urefs_t refs=0;
    kern_return_t t=mach_port_type(mach_task_self(),port,&type),q=mach_port_get_refs(mach_task_self(),port,MACH_PORT_RIGHT_SEND_ONCE,&refs);
    printf("REPLY_CAPABILITY mode=%s expects=%d port=%u type_status=%d type=%u refs_status=%d refs=%u\n",xpc_dictionary_get_string(request,"mode"),expects,port,t,type,q,refs);fflush(stdout);
    if(!expects){puts("REPLY_CAPABILITY_MISSING");fflush(stdout);exit(1);}
    xpc_object_t response=xpc_dictionary_create_reply(request);if(!response)exit(2);
    xpc_connection_t requestPeer=xpc_dictionary_get_remote_connection(request),replyPeer=xpc_dictionary_get_remote_connection(response);
    printf("REPLY_REMOTE_CONNECTION mode=%s request_matches=%d reply_matches=%d\n",xpc_dictionary_get_string(request,"mode"),requestPeer==peer,replyPeer==peer);fflush(stdout);
    if(requestPeer!=peer||replyPeer!=peer){puts("REPLY_REMOTE_CONNECTION_MISSING");fflush(stdout);exit(1);}
    if(expects_reply(request)||xpc_dictionary_create_reply(request)||xpc_dictionary_create_reply(response))exit(5);
    xpc_dictionary_set_int64(response,"nonce",xpc_dictionary_get_int64(request,"nonce"));xpc_connection_send_message(replyPeer,response);xpc_release(response);
   });
   xpc_connection_resume(peer);
  });xpc_connection_resume(listener);
  xpc_endpoint_t endpoint=xpc_endpoint_create(listener);xpc_connection_t client=xpc_connection_create_from_endpoint(endpoint);xpc_release(endpoint);
  xpc_connection_set_event_handler(client,^(xpc_object_t e){(void)e;});xpc_connection_resume(client);
  xpc_object_t request=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_string(request,"mode","sync");xpc_dictionary_set_int64(request,"nonce",81237);
  xpc_object_t reply=xpc_connection_send_message_with_reply_sync(client,request);
  if(!reply||xpc_get_type(reply)!=XPC_TYPE_DICTIONARY||xpc_dictionary_get_int64(reply,"nonce")!=81237)return 3;
  xpc_release(reply);xpc_release(request);
  dispatch_semaphore_t done=dispatch_semaphore_create(0);__block BOOL valid=NO;
  request=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_string(request,"mode","async");xpc_dictionary_set_int64(request,"nonce",55123);
  xpc_connection_send_message_with_reply(client,request,NULL,^(xpc_object_t response){valid=xpc_get_type(response)==XPC_TYPE_DICTIONARY&&xpc_dictionary_get_int64(response,"nonce")==55123;dispatch_semaphore_signal(done);});xpc_release(request);
  if(dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC))||!valid)return 4;
  puts("XPC_REAL_SYNC_AND_ASYNC_REPLY_CAPABILITIES_NATIVE_OK");
 }
 return 0;
}
