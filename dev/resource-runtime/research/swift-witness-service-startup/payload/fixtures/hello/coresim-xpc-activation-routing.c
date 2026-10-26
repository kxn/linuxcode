#include <dlfcn.h>
#include <xpc/xpc.h>
#include <dispatch/dispatch.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 assert(argc==2);void *module=dlopen(argv[1],RTLD_LAZY|RTLD_LOCAL);if(!module){fprintf(stderr,"ROUTING_LOAD_ERROR %s\n",dlerror());return 2;}
 unsigned char *method=dlsym(module,"$s22CoreSimulatorUtilities19XPCConnectionObjectPAAE8activateyyF");assert(method && !memcmp(method,"\x55\x48\x89\xe5\x48\x8b\x15",7));int32_t displacement;memcpy(&displacement,method+7,4);void *bound;memcpy(&bound,method+11+displacement,sizeof(bound));void *global=dlsym(RTLD_DEFAULT,"xpc_connection_activate");
 Dl_info info={0},other={0};assert(bound && global && dladdr(bound,&info) && dladdr(global,&other));printf("ACTIVATE_BOUND address=%p owner=%s symbol=%s\n",bound,info.dli_fname,info.dli_sname?info.dli_sname:"(unknown)");printf("ACTIVATE_GLOBAL address=%p owner=%s symbol=%s same=%d\n",global,other.dli_fname,other.dli_sname?other.dli_sname:"(unknown)",bound==global);
 xpc_connection_t own=xpc_connection_create_mach_service("com.apple.CoreSimulator.linuxcode.owned-activation",NULL,XPC_CONNECTION_MACH_SERVICE_LISTENER);assert(own);xpc_connection_set_event_handler(own,^(xpc_object_t event){(void)event;});puts("ACTIVATE_CALLING_ORIGINAL_BOUND_POINTER");fflush(stdout);((void(*)(xpc_connection_t))bound)(own);puts("ACTIVATE_BOUND_RETURNED");fflush(stdout);xpc_connection_cancel(own);xpc_release(own);return bound==global?0:3;
}
