#import <Foundation/Foundation.h>
#include <xpc/xpc.h>
#include <xpc/connection.h>
#include <dispatch/dispatch.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#define N 32
struct state {unsigned callbacks,finalized;};
static struct state states[2*N];
static xpc_object_t pending[N];
static unsigned requests,callbacks,finalized,errors;
static dispatch_semaphore_t received,completed,retired;
static void fail(const char* text,int line){fprintf(stderr,"XPC_LIFETIME_FAIL line=%d %s\n",line,text);exit(1);}
#define CHECK(x) do{if(!(x))fail(#x,__LINE__);}while(0)
static void finalizer(void* opaque){struct state* s=opaque;__atomic_add_fetch(&s->finalized,1,__ATOMIC_RELAXED);__atomic_add_fetch(&finalized,1,__ATOMIC_RELAXED);dispatch_semaphore_signal(retired);}
int main(void){@autoreleasepool{
 alarm(30);setbuf(stdout,NULL);received=dispatch_semaphore_create(0);completed=dispatch_semaphore_create(0);retired=dispatch_semaphore_create(0);
 xpc_connection_t listener=xpc_connection_create(NULL,NULL);
 xpc_connection_set_event_handler(listener,^(xpc_object_t peer){
  if(xpc_get_type(peer)!=XPC_TYPE_CONNECTION)return;
  xpc_connection_set_event_handler(peer,^(xpc_object_t request){
   if(xpc_get_type(request)!=XPC_TYPE_DICTIONARY)return;
   unsigned nonce=(unsigned)xpc_dictionary_get_uint64(request,"nonce");
   if(nonce>=N)return; /* cancellation phase may race message delivery */
   xpc_object_t reply=xpc_dictionary_create_reply(request);if(!reply){__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);return;}
   xpc_dictionary_set_uint64(reply,"nonce",nonce);pending[nonce]=reply;
   __atomic_add_fetch(&requests,1,__ATOMIC_RELEASE);dispatch_semaphore_signal(received);
  });xpc_connection_resume(peer);
 });xpc_connection_resume(listener);xpc_endpoint_t endpoint=xpc_endpoint_create(listener);
 for(unsigned i=0;i<2*N;i++){
  xpc_connection_t client=xpc_connection_create_from_endpoint(endpoint);xpc_connection_set_context(client,&states[i]);xpc_connection_set_finalizer_f(client,finalizer);
  xpc_connection_set_event_handler(client,^(xpc_object_t e){(void)e;});xpc_connection_resume(client);
  xpc_object_t message=xpc_dictionary_create(NULL,NULL,0);xpc_dictionary_set_uint64(message,"nonce",i);
  xpc_connection_send_message_with_reply(client,message,NULL,^(xpc_object_t reply){
   if(__atomic_add_fetch(&states[i].callbacks,1,__ATOMIC_RELAXED)!=1)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   if(i<N ? (xpc_get_type(reply)!=XPC_TYPE_DICTIONARY || xpc_dictionary_get_uint64(reply,"nonce")!=i) : xpc_get_type(reply)!=XPC_TYPE_ERROR)__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   if(__atomic_load_n(&states[i].finalized,__ATOMIC_ACQUIRE))__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);
   __atomic_add_fetch(&callbacks,1,__ATOMIC_RELEASE);dispatch_semaphore_signal(completed);
  });xpc_release(message);
  if(i>=N)xpc_connection_cancel(client);
  xpc_release(client); /* pending async context must keep its raw hook alive */
 }
 for(unsigned i=0;i<N;i++)CHECK(dispatch_semaphore_wait(received,dispatch_time(DISPATCH_TIME_NOW,8*NSEC_PER_SEC))==0);
 CHECK(requests==N);
 for(unsigned i=0;i<N;i++)CHECK(!__atomic_load_n(&states[i].finalized,__ATOMIC_ACQUIRE));
 for(unsigned i=0;i<N;i++){CHECK(pending[i]);xpc_connection_send_message(xpc_dictionary_get_remote_connection(pending[i]),pending[i]);xpc_release(pending[i]);}
 for(unsigned i=0;i<2*N;i++)CHECK(dispatch_semaphore_wait(completed,dispatch_time(DISPATCH_TIME_NOW,8*NSEC_PER_SEC))==0);
 for(unsigned i=0;i<2*N;i++)CHECK(dispatch_semaphore_wait(retired,dispatch_time(DISPATCH_TIME_NOW,8*NSEC_PER_SEC))==0);
 CHECK(callbacks==2*N && finalized==2*N && !errors);
 for(unsigned i=0;i<2*N;i++)CHECK(states[i].callbacks==1 && states[i].finalized==1);
 puts("XPC_ASYNC_RELEASE_BEFORE_REPLY_AND_CANCEL_EXACTLY_ONCE_LIFETIME_OK replies=32 cancelled=32 finalized=64");
 xpc_release(endpoint);xpc_connection_cancel(listener);xpc_release(listener);
}return 0;}
