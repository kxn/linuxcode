#include <errno.h>
#include <fcntl.h>
#include <mach-o/dyld_images.h>
#include <mach/mach.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>

static int bootstrap_fcntl(int fd,int command,...) {
    task_dyld_info_data_t info={0};mach_msg_type_number_t count=TASK_DYLD_INFO_COUNT;
    if(task_info(mach_task_self(),TASK_DYLD_INFO,(task_info_t)&info,&count)!=KERN_SUCCESS){errno=ENOEXEC;return -1;}
    const struct dyld_all_image_infos* images=(void*)info.all_image_info_addr;
    const unsigned char* loader=(const unsigned char*)images->dyldImageLoadAddress;
    if(!loader || *(const uint32_t*)loader!=0xfeedfacf){errno=ENOEXEC;return -1;}
    // This private source component is pinned to the packaged Intel loader.
    // Its fcntl syscall entry remains at the original address, 0xf3390.
    long (*entry)(int,int,long)=(void*)(loader+0xf3390);
    printf("BOOTSTRAP_ENTRY_BYTES %02x%02x%02x%02x%02x\n",loader[0xf3390],loader[0xf3391],loader[0xf3392],loader[0xf3393],loader[0xf3394]);
    va_list args;va_start(args,command);void* input=va_arg(args,void*);va_end(args);
    long result=entry(fd,command,(long)input);
    printf("BOOTSTRAP_STATIC_FCNTL_ACTIVE command=%d result=%ld\n",command,result);
    if(result<0){errno=-result;return -1;}return result;
}
#define fcntl bootstrap_fcntl
#include "simulator-dyld-signature-native.c"
