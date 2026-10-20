#include <dlfcn.h>
#include <mach/mach.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef kern_return_t (*get_io_port)(host_t,mach_port_t *);
static int checks;
#define CHECK(v) do {++checks;if(!(v)){printf("IO_MAIN_FAILED %d %s\n",__LINE__,#v);return 13;}} while(0)
int main(int argc,char **argv) {
    if(argc!=2)return 10;
    get_io_port main_port=dlsym(RTLD_DEFAULT,"host_get_io_main");
    get_io_port old_port=dlsym(RTLD_DEFAULT,"host_get_io_master");
    if(!main_port){puts("IO_MAIN_MISSING");return 12;}
    Dl_info provider;CHECK(dladdr((void*)main_port,&provider));
    printf("IO_MAIN_PROVIDER %s\n",provider.dli_fname);
    CHECK(strstr(provider.dli_fname,"libsystem_kernel.dylib"));CHECK(old_port);
    mach_port_t port=0x123456,old_invalid=0x123456;
    kern_return_t null_main=main_port(MACH_PORT_NULL,&port);
    kern_return_t null_old=old_port(MACH_PORT_NULL,&old_invalid);
    printf("IO_MAIN_NULL_HOST %d %d\n",null_main,null_old);
    CHECK(null_main==MACH_SEND_INVALID_DEST && null_main==null_old);
    mach_port_t host=mach_host_self();CHECK(MACH_PORT_VALID(host));
    for(int i=0;i<16;++i) {
        mach_port_t a=MACH_PORT_NULL,b=MACH_PORT_NULL;mach_port_type_t type=0;
        kern_return_t first=main_port(host,&a),second=old_port(host,&b);
        printf("IO_MAIN_PORT %d %u %d %u\n",first,a,second,b);
        CHECK(first==KERN_SUCCESS);CHECK(second==first);CHECK(a==b);
        if(MACH_PORT_VALID(a)) {
            CHECK(mach_port_type(mach_task_self(),a,&type)==KERN_SUCCESS);CHECK(type&MACH_PORT_TYPE_SEND);
            CHECK(mach_port_deallocate(mach_task_self(),a)==KERN_SUCCESS);CHECK(mach_port_deallocate(mach_task_self(),b)==KERN_SUCCESS);
        } else {CHECK(a==MACH_PORT_NULL && b==MACH_PORT_NULL);}
    }
    CHECK(mach_port_deallocate(mach_task_self(),host)==KERN_SUCCESS);
    if(checks!=atoi(argv[1])){puts("IO_MAIN_WRONG_COUNT_REJECTED");return 15;}
    printf("IO_MAIN_MIG_COMPAT_OK %d\n",checks);return 0;
}
