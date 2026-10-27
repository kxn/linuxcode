#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static __attribute__((noinline)) unsigned exercise_stack(void) {
 volatile unsigned char bytes[512*1024];unsigned sum=0;
 for(unsigned i=0;i<sizeof(bytes);i+=4096){bytes[i]=(i/4096)%251;sum+=bytes[i];}
 return sum;
}
static void* worker(void* p){return (void*)(uintptr_t)(exercise_stack()+1);}
int main(int argc,char** argv) {
 uintptr_t sp;__asm__("mov %%rsp,%0":"=r"(sp));
 fprintf(stderr,"MLDR_NATIVE_ENTER_MAIN SP=%p\n",(void*)sp);
 if(argc>1&&!strcmp(argv[1],"--forced")) {
  assert(sp<0x7fffffe00000UL-65536);
  volatile unsigned char* prior=(void*)(uintptr_t)(0x7fffffe00000UL-65536);
  assert(prior[0]==0xa5&&prior[65535]==0x5a);
 }
 assert(sp<(uintptr_t)pthread_get_stackaddr_np(pthread_self()));
 unsigned expected=exercise_stack();assert(expected>0);
 pthread_attr_t attr;assert(pthread_attr_init(&attr)==0);
 assert(pthread_attr_setstacksize(&attr,1024*1024)==0);
 pthread_t thread;assert(pthread_create(&thread,&attr,worker,NULL)==0);
 assert(pthread_attr_destroy(&attr)==0);
 void* result;assert(pthread_join(thread,&result)==0);assert((uintptr_t)result==expected+1);
 puts("MLDR_NATIVE_MAIN_STACK_COLLISION_512K_CAPACITY_MARKERS_AND_PTHREAD_OK");
 return 0;
}
