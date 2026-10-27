#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <sys/mman.h>
#include <unistd.h>
/* Diagnostic fault injection only. Production uses the source-built loader. */
__attribute__((constructor)) static void occupy_preferred_stack(void) {
 const size_t size=65536;void* address=(void*)(uintptr_t)(0x7fffffe00000UL-size);
 void* p=mmap(address,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 if(p==address){volatile unsigned char* b=p;b[0]=0xa5;b[size-1]=0x5a;const char s[]="MLDR_FORCED_STACK_COLLISION_RESERVED\n";write(2,s,sizeof(s)-1);}
 sleep(2); /* Let the host tracer attach before this diagnostic loader runs. */
}
