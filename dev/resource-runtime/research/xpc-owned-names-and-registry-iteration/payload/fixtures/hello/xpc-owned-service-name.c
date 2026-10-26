#include <xpc/xpc.h>
#include <xpc/connection.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
 int failures=0;
 for(unsigned i=0;i<2;++i){
  const char *expected=i?"org.linuxcode.owned-name.listener":"org.linuxcode.owned-name.client";
  char *caller=strdup(expected);if(!caller)return 2;
  xpc_connection_t connection=xpc_connection_create_mach_service(caller,NULL,i?XPC_CONNECTION_MACH_SERVICE_LISTENER:0);
  if(!connection)return 3;
  xpc_connection_set_event_handler(connection,^(xpc_object_t event){(void)event;});
  memset(caller,'x',strlen(caller));
  const char *actual=xpc_connection_get_name(connection);int preserved=actual&&!strcmp(actual,expected);
  printf("OWNED_SERVICE_NAME listener=%u preserved=%d actual=%s\n",i,preserved,actual?actual:"NULL");
  if(preserved)free(caller);
  if(preserved && strcmp(xpc_connection_get_name(connection),expected))return 4;
  if(!preserved)++failures;
  xpc_connection_cancel(connection);xpc_release(connection);
 }
 printf("OWNED_SERVICE_NAME_FAILURES %d\n",failures);
 if(!failures)puts("XPC_COPIES_CALLER_SERVICE_NAMES_NATIVE_OK");
 return failures?1:0;
}
