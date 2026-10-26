#import <Foundation/Foundation.h>
#import <objc/message.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <stdio.h>
int main(int argc,char **argv) {
 if(argc!=3)return 2;
 @autoreleasepool {
  if(!dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL)){fprintf(stderr,"DLOPEN %s\n",dlerror());return 3;}
  Class cls=NSClassFromString(@"DIAttachedDeviceInfo");if(!cls)return 4;
  const char *names[]={"IOHDIXController","AppleDiskImagesController"};
  const char *selectors[]={"newDI1DevicesArrayWithError:","newDI2DevicesArrayWithError:"};
  io_registry_entry_t root=IORegistryGetRootEntry(kIOMasterPortDefault);uint64_t rootID=0;
  if(!root||IORegistryEntryGetRegistryEntryID(root,&rootID))return 7;
  IOObjectRelease(root);
  for(unsigned i=0;i<2;++i){
   io_service_t service=IOServiceGetMatchingService(kIOMasterPortDefault,IOServiceMatching(names[i]));
   if(!service)return 5;
   io_iterator_t iterator=0;
   if(IORegistryEntryCreateIterator(service,kIOServicePlane,0,&iterator)||!iterator||IOIteratorNext(iterator))return 8;
   IOObjectRelease(iterator);
   if(IORegistryEntryCreateIterator(service,kIOServicePlane,kIORegistryIterateParents,&iterator)||!iterator)return 9;
   io_registry_entry_t parent=IOIteratorNext(iterator);uint64_t parentID=0;
   if(!parent||IORegistryEntryGetRegistryEntryID(parent,&parentID)||parentID!=rootID||IOIteratorNext(iterator))return 10;
   IOObjectRelease(parent);IOObjectRelease(iterator);
   iterator=0;
   if(IORegistryEntryCreateIterator(service,kIOServicePlane,0x40000000,&iterator)!=kIOReturnUnsupported||iterator)return 11;
   IOObjectRelease(service);
   NSError *error=nil;NSArray *devices=((id(*)(id,SEL,NSError**))objc_msgSend)(cls,sel_registerName(selectors[i]),&error);
   printf("ORIGINAL_DISK_GENERATION %u array=%d count=%lu error=%ld\n",i+1,devices!=nil,(unsigned long)devices.count,(long)error.code);
   if(error)printf("ORIGINAL_DISK_ERROR %s\n",error.description.UTF8String);
   if(!devices||devices.count||error)return 6;[devices release];
  }
  puts("ORIGINAL_DI1_DI2_EMPTY_ENUMERATION_NATIVE_OK");
 }
 return 0;
}
