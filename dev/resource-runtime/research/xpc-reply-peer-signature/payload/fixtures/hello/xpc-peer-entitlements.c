#include <xpc/xpc.h>
#include <xpc/connection.h>
#include <dispatch/dispatch.h>
#include <mach/mach.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <assert.h>
static xpc_object_t (*copy_value)(xpc_connection_t,const char*);
static void (*copy_token)(xpc_connection_t,audit_token_t*);
static xpc_object_t (*copy_token_value)(const char*,audit_token_t*);
static int peer_values(xpc_connection_t conn,int signed_peer) {
 const char *keys[]={"org.linuxcode.peer.true","org.linuxcode.peer.false","org.linuxcode.peer.string","org.linuxcode.peer.number","org.linuxcode.peer.array","org.linuxcode.peer.nested","org.linuxcode.peer.absent"};
 for(unsigned i=0;i<7;++i) {
  xpc_object_t v=copy_value(conn,keys[i]);
  if(!signed_peer||i==6){if(v){xpc_release(v);return 1;}continue;}
  if(!v)return 2;int ok=0;
  switch(i){
   case 0:ok=xpc_get_type(v)==XPC_TYPE_BOOL&&xpc_bool_get_value(v);break;
   case 1:ok=xpc_get_type(v)==XPC_TYPE_BOOL&&!xpc_bool_get_value(v);break;
   case 2:ok=xpc_get_type(v)==XPC_TYPE_STRING&&!strcmp(xpc_string_get_string_ptr(v),"signed-peer-value");break;
   case 3:ok=xpc_get_type(v)==XPC_TYPE_INT64&&xpc_int64_get_value(v)==947;break;
   case 4:ok=xpc_get_type(v)==XPC_TYPE_ARRAY&&xpc_array_get_count(v)==2&&!strcmp(xpc_array_get_string(v,0),"entry")&&xpc_array_get_bool(v,1);break;
   case 5:ok=xpc_get_type(v)==XPC_TYPE_DICTIONARY&&xpc_dictionary_get_int64(v,"number")==18;break;
  }xpc_release(v);if(!ok)return 3;
 }
 audit_token_t token;copy_token(conn,&token);printf("PEER_SIGNATURE_ID pid=%u version=%u own=%d\n",token.val[5],token.val[7],getpid());fflush(stdout);
 if(token.val[5]==(unsigned)getpid()||!token.val[7]||token.val[7]==~0U)return 4;
 token.val[7]^=0x40000000U;if(copy_token_value("org.linuxcode.peer.true",&token))return 5;
 token.val[5]=0;if(copy_token_value("org.linuxcode.peer.true",&token))return 6;
 return 0;
}
int main(int argc,char **argv) {
 if(argc!=4)return 20;
 copy_value=dlsym(RTLD_DEFAULT,"xpc_connection_copy_entitlement_value");copy_token=dlsym(RTLD_DEFAULT,"xpc_connection_get_audit_token");copy_token_value=dlsym(RTLD_DEFAULT,"xpc_copy_entitlement_for_token");if(!copy_value||!copy_token||!copy_token_value)return 21;
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,15*NSEC_PER_SEC),dispatch_get_global_queue(0,0),^{fputs("PEER_SIGNATURE_TIMEOUT\n",stderr);exit(22);});
 if(!strcmp(argv[1],"--server")) {
  xpc_connection_t listener=xpc_connection_create_mach_service(argv[2],NULL,XPC_CONNECTION_MACH_SERVICE_LISTENER);
  xpc_connection_set_event_handler(listener,^(xpc_object_t peer){
   if(xpc_get_type(peer)!=XPC_TYPE_CONNECTION)return;
   xpc_connection_set_event_handler(peer,^(xpc_object_t request){
    if(xpc_get_type(request)!=XPC_TYPE_DICTIONARY)return;
    xpc_object_t client=copy_value(peer,"org.linuxcode.client");
    int valid=client&&xpc_get_type(client)==XPC_TYPE_STRING&&!strcmp(xpc_string_get_string_ptr(client),"separate-client-value");if(client)xpc_release(client);
    xpc_object_t reply=xpc_dictionary_create_reply(request);if(!reply)exit(23);
    xpc_dictionary_set_bool(reply,"client-signature-matches",valid);
    xpc_dictionary_set_int64(reply,"nonce",xpc_dictionary_get_int64(request,"nonce"));
    xpc_connection_send_message(xpc_dictionary_get_remote_connection(reply),reply);xpc_release(reply);
   });xpc_connection_resume(peer);
  });xpc_connection_resume(listener);dispatch_main();
 }
 xpc_connection_t client=xpc_connection_create_mach_service(argv[2],NULL,0);xpc_connection_set_event_handler(client,^(xpc_object_t event){(void)event;});xpc_connection_resume(client);
 int signed_peer=!strcmp(argv[3],"signed");
 xpc_object_t request=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_int64(request,"nonce",1319);
 xpc_object_t reply=xpc_connection_send_message_with_reply_sync(client,request);
 if(!reply||xpc_get_type(reply)!=XPC_TYPE_DICTIONARY||xpc_dictionary_get_int64(reply,"nonce")!=1319||!xpc_dictionary_get_bool(reply,"client-signature-matches"))return 24;
 xpc_release(reply);xpc_release(request);int status=peer_values(client,signed_peer);printf("PEER_SIGNATURE_SYNC_STATUS %d\n",status);fflush(stdout);if(status)return 30+status;
 dispatch_semaphore_t done=dispatch_semaphore_create(0);__block int async_status=0;
 request=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_int64(request,"nonce",2713);
 xpc_connection_send_message_with_reply(client,request,NULL,^(xpc_object_t response){
  if(xpc_get_type(response)!=XPC_TYPE_DICTIONARY||xpc_dictionary_get_int64(response,"nonce")!=2713||!xpc_dictionary_get_bool(response,"client-signature-matches"))async_status=1;
  else async_status=peer_values(client,signed_peer);
  dispatch_semaphore_signal(done);
 });xpc_release(request);
 if(dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC)))return 25;
 printf("PEER_SIGNATURE_ASYNC_STATUS %d\n",async_status);if(async_status)return 40+async_status;
 puts(signed_peer?"XPC_SIGNED_PEER_METADATA_NATIVE_OK":"XPC_UNSIGNED_PEER_METADATA_ABSENT_NATIVE_OK");return 0;
}
