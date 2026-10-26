#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_host.h>
#include <stdint.h>
#include <stdio.h>
struct recipe {uint32_t key,command,previous,size;};
int main(void){
 setbuf(stdout,NULL);typedef kern_return_t(*create_t)(mach_port_t,unsigned char*,unsigned,mach_port_t*);
 create_t normal=dlsym(RTLD_DEFAULT,"host_create_mach_voucher"),mig=dlsym(RTLD_DEFAULT,"_kernelrpc_host_create_mach_voucher");
 if(!normal||!mig){printf("VOUCHER_ENTRY_MISSING normal=%d mig=%d\n",!!normal,!!mig);return 2;}
 struct recipe bank={3,610,0,0};mach_port_t port=0;host_t host=mach_host_self();
 kern_return_t rc=normal(host,(void*)&bank,sizeof bank,&port);printf("VOUCHER_BANK_PUBLIC result=%d port=%u\n",rc,port);
 if(!rc&&port)mach_port_deallocate(mach_task_self(),port);
 port=0;rc=mig(host,NULL,0,&port);printf("VOUCHER_EMPTY_MIG result=%d port=%u\n",rc,port);
 port=0;rc=mig(host,(void*)&bank,sizeof bank,&port);printf("VOUCHER_BANK_MIG result=%d port=%u\n",rc,port);
 if(!rc&&port){mach_port_type_t type=0;kern_return_t check=mach_port_type(mach_task_self(),port,&type);printf("VOUCHER_BANK_PORT_TYPE result=%d type=%x\n",check,type);mach_port_deallocate(mach_task_self(),port);}
 puts("VOUCHER_BANK_REAL_FAST_AND_MIG_PATHS_CAPTURED");return 0;
}
