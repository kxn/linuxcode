#import <Foundation/Foundation.h>
#import <objc/message.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOReturn.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
extern kern_return_t host_get_io_main(host_t,mach_port_t*);
int main(int argc,char **argv) {
 if(argc!=3)return 2;
 BOOL expected=!strcmp(argv[2],"present");
 @autoreleasepool {
  Dl_info owner={0};dladdr(IOServiceGetMatchingService,&owner);
  mach_port_t master=0;kern_return_t port_status=IOMasterPort(MACH_PORT_NULL,&master);
  io_iterator_t all=0;kern_return_t all_status=IOServiceGetMatchingServices(master,IOServiceMatching("IOService"),&all);
  printf("REGISTRY_BACKEND owner=%s port_status=%d master=%u all_status=%d iterator=%u\n",owner.dli_fname,port_status,master,all_status,all);
  if(expected){
   mach_port_t port=0;host_t host=mach_host_self();kern_return_t modern=host_get_io_main(host,&port);
   printf("REGISTRY_MODERN_HOST_PORT status=%d port=%u\n",modern,port);
   if(modern || !port || port!=master)return 12;
   mach_port_deallocate(mach_task_self(),port);mach_port_deallocate(mach_task_self(),host);
   if(host_get_io_main(MACH_PORT_NULL,&port)==KERN_SUCCESS || host_get_io_main(mach_host_self(),NULL)==KERN_SUCCESS)return 13;
  }
  if(all){io_object_t item;while((item=IOIteratorNext(all))){io_name_t name={0};IOObjectGetClass(item,name);printf("REGISTRY_CLASS %s\n",name);IOObjectRelease(item);}IOObjectRelease(all);}
  io_service_t service=IOServiceGetMatchingService(kIOMasterPortDefault,IOServiceMatching("AppleDiskImagesController"));
  printf("CONTROLLER_PRESENT %d\n",service!=0);
  fflush(stdout);if(getenv("LINUXCODE_CONTROLLER_PAUSE"))sleep(25);
  if((service!=0)!=expected)return 3;
  if(service){
   uint64_t id1=0;IORegistryEntryGetRegistryEntryID(service,&id1);
   io_iterator_t children=0;kern_return_t kr=IORegistryEntryGetChildIterator(service,kIOServicePlane,&children);
   if(kr||!children)return 4;
   io_object_t child=IOIteratorNext(children);if(child){IOObjectRelease(child);return 5;}
   IOObjectRelease(children);
   io_connect_t connection=0;kr=IOServiceOpen(service,mach_task_self(),0,&connection);
   printf("CONTROLLER_ATTACH_OPEN status=%d connection=%u\n",kr,connection);
   if(kr!=kIOReturnUnsupported||connection)return 6;
   io_service_t again=IOServiceGetMatchingService(kIOMasterPortDefault,IOServiceMatching("AppleDiskImagesController"));
   uint64_t id2=0;if(!again||IORegistryEntryGetRegistryEntryID(again,&id2)||id1!=id2)return 7;
   IOObjectRelease(again);IOObjectRelease(service);
  }
  if(!dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL)){fprintf(stderr,"DLOPEN %s\n",dlerror());return 8;}
  Class cls=NSClassFromString(@"DIAttachedDeviceInfo");if(!cls)return 9;
  NSError *error=nil;
  NSArray *devices=((id(*)(id,SEL,NSError**))objc_msgSend)(cls,sel_registerName("newDI2DevicesArrayWithError:"),&error);
  printf("ORIGINAL_DI2_ENUM array=%d count=%lu error_domain=%s error_code=%ld\n",devices!=nil,(unsigned long)devices.count,error?error.domain.UTF8String:"none",(long)error.code);
  if(expected && (!devices||devices.count||error))return 10;
  if(!expected && (devices||!error||error.code!=153))return 11;
  [devices release];
  puts(expected?"ORIGINAL_DI2_EMPTY_REGISTRY_NATIVE_OK":"ORIGINAL_DI2_MISSING_CONTROLLER_CONTROL_OK");
 }
 return 0;
}
