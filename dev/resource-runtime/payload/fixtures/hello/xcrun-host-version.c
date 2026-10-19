#include <stdio.h>
#include <stdint.h>
#include <dlfcn.h>
#include <mach-o/loader.h>
extern const struct mach_header* dyld_image_header_containing_address(const void*);
extern void dyld_get_image_versions(const struct mach_header*,void(^)(uint32_t,uint32_t,uint32_t));
int main(void){
 void *function=(void*)dyld_image_header_containing_address;Dl_info info={0};
 if(!dladdr(function,&info))return 1;
 const struct mach_header *header=dyld_image_header_containing_address(function);if(!header)return 2;
 printf("XCRUN_HOST_PROVIDER %s\n",info.dli_fname);
 __block int callbacks=0;
 dyld_get_image_versions(header,^(uint32_t platform,uint32_t sdk,uint32_t minimum){
  printf("XCRUN_HOST_VERSION %u %u %u\n",platform,sdk,minimum);callbacks++;
 });
 printf("XCRUN_HOST_CALLBACKS %d\n",callbacks);return callbacks?0:3;
}
