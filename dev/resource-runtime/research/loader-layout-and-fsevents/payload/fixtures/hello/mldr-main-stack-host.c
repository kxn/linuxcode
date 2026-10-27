#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>
#include "../../vendor/darling/src/startup/mldr/main-stack.h"
int main(void) {
 const size_t initial=65536,capacity=8*1024*1024;
 uintptr_t top=0x7fffffe00000UL;
 /* Find a vacant window without replacing any host mapping. */
 void* window=MAP_FAILED;
 for(unsigned i=0;i<64;i++){
  top=0x7fffffe00000UL-i*32UL*1024*1024;
  window=mmap((void*)(top-capacity),capacity,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED_NOREPLACE,-1,0);
  if(window!=MAP_FAILED)break;
 }
 assert(window!=MAP_FAILED);assert(munmap(window,capacity)==0);
 uintptr_t ceiling=top;
 void* normal=mldr_allocate_main_stack(&top,initial,capacity,mmap);
 assert(normal==(void*)(ceiling-initial)&&top==ceiling);assert(munmap(normal,initial)==0);
 unsigned char* occupied=mmap((void*)(ceiling-initial),initial,PROT_READ|PROT_WRITE,MAP_ANONYMOUS|MAP_PRIVATE|MAP_FIXED_NOREPLACE,-1,0);
 assert(occupied!=MAP_FAILED);occupied[0]=0xa5;occupied[initial-1]=0x5a;
 top=ceiling;unsigned char* fallback=mldr_allocate_main_stack(&top,initial,capacity,mmap);
 assert(fallback!=MAP_FAILED&&fallback!=occupied&&top<=ceiling);
 assert(top-(uintptr_t)fallback==capacity);
 assert(occupied[0]==0xa5&&occupied[initial-1]==0x5a);
 /* Exercise the full reservation, well beyond the original 64 KiB. */
 fallback[0]=0x12;fallback[capacity-1]=0x34;fallback[capacity/2]=0x56;
 assert(fallback[0]==0x12&&fallback[capacity-1]==0x34&&fallback[capacity/2]==0x56);
 assert(munmap(fallback,capacity)==0);assert(munmap(occupied,initial)==0);
 top=ceiling;errno=0;assert(mldr_allocate_main_stack(&top,initial,initial-1,mmap)==MAP_FAILED&&errno==EINVAL&&top==ceiling);
 puts("MLDR_MAIN_STACK_PREFERRED_COLLISION_FULL_CAPACITY_AND_LIVE_MAPPING_PRESERVED_OK");
}
