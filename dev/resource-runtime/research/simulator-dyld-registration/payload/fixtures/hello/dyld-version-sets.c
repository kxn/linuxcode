#include <mach-o/loader.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
typedef struct { uint32_t platform,version; } build_version;
static bool (*sdk_at_least)(const struct mach_header*,build_version);
static bool (*min_at_least)(const struct mach_header*,build_version);
static bool (*program_sdk)(build_version);
static bool (*program_min)(build_version);
static const struct mach_header* (*header_for_handle)(void*);
static void check_image(const struct mach_header *h,unsigned min,unsigned sdk){
 struct {uint32_t set,macos;} cases[]={
  {0x07db0901,0x000a0700},{0x07e50901,0x000c0000},{0x07e70901,0x000e0000},
  {0x07e70c01,0x000e0100},{0x07e80000,0x000f0000},{0x07e90000,0x00100000},
  {0x07e90100,0x001a0100},{0x07e90400,0x001a0400},{0x07e90500,0x001a0500},{0x07e90600,0x001a0600}
 };
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i){
  build_version epoch={~0U,cases[i].set},concrete={1,cases[i].macos};
  assert(sdk_at_least(h,epoch)==(sdk>=concrete.version));assert(min_at_least(h,epoch)==(min>=concrete.version));
  assert(sdk_at_least(h,epoch)==sdk_at_least(h,concrete));assert(min_at_least(h,epoch)==min_at_least(h,concrete));
 }
 assert(!sdk_at_least(h,(build_version){~0U,0xffffffff}));assert(!min_at_least(h,(build_version){~0U,0xffffffff}));
 assert(!sdk_at_least(h,(build_version){2,0x10000}));assert(!min_at_least(h,(build_version){2,0x10000}));
 printf("DYLD_REAL_IMAGE_VERSION_SETS min=%x sdk=%x cases=%zu\n",min,sdk,sizeof(cases)/sizeof(cases[0]));
}
int main(int argc,char **argv){
 assert(argc==4);sdk_at_least=dlsym(RTLD_DEFAULT,"dyld_sdk_at_least");min_at_least=dlsym(RTLD_DEFAULT,"dyld_minos_at_least");program_sdk=dlsym(RTLD_DEFAULT,"dyld_program_sdk_at_least");program_min=dlsym(RTLD_DEFAULT,"dyld_program_minos_at_least");header_for_handle=dlsym(RTLD_DEFAULT,"_dyld_get_dlopen_image_header");assert(sdk_at_least&&min_at_least&&program_sdk&&program_min&&header_for_handle);
 unsigned mins[]={0xb0000,0xe0000,0x1a0000},sdks[]={0xb0000,0xe0000,0x1a0500};
 for(unsigned i=0;i<3;++i){void*h=dlopen(argv[i+1],RTLD_LAZY|RTLD_LOCAL);if(!h){fprintf(stderr,"DLOPEN %s\n",dlerror());return 2;}check_image(header_for_handle(h),mins[i],sdks[i]);assert(!dlclose(h));}
 assert(program_sdk((build_version){~0U,0x7e90500}));assert(!program_sdk((build_version){~0U,0x7e90600}));assert(!program_sdk((build_version){~0U,0xffffffff}));
 assert(program_min((build_version){~0U,0x7e40901}));assert(!program_min((build_version){~0U,0x7e50901}));assert(!program_min((build_version){~0U,0xffffffff}));
 puts("DYLD_MODERN_EPOCHS_REAL_IMAGES_AND_MAIN_FAST_PATH_NATIVE_OK");return 0;
}
