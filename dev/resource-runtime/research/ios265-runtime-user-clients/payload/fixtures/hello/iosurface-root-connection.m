#import <Foundation/Foundation.h>
#include <IOKit/IOKitLib.h>
#include <mach/mach.h>
#include <stdio.h>
int main(void) {
 @autoreleasepool {
  const char *names[]={"IOSurfaceRoot","IOCoreSurfaceRoot"};
  for(unsigned i=0;i<2;++i) {
   io_service_t service=IOServiceGetMatchingService(kIOMasterPortDefault,IOServiceMatching(names[i]));
   printf("IOSURFACE_ROOT_MATCH %s port=%u\n",names[i],service);fflush(stdout);
   if(!service)continue;
   io_name_t cls={0};kern_return_t c=IOObjectGetClass(service,cls);printf("IOSURFACE_ROOT_CLASS status=%x class=%s\n",c,cls);
   io_connect_t connection=0;kern_return_t status=IOServiceOpen(service,mach_task_self(),0,&connection);
   printf("IOSURFACE_ROOT_OPEN status=%x connection=%u\n",status,connection);fflush(stdout);
   if(connection){
    io_connect_t second=0;if(IOServiceOpen(service,mach_task_self(),0,&second)||!second||second==connection||connection==service)return 2;
    io_service_t backing=0;if(IOConnectGetService(connection,&backing)||!backing)return 3;
    uint64_t before=0,after=0;if(IORegistryEntryGetRegistryEntryID(service,&before)||IORegistryEntryGetRegistryEntryID(backing,&after)||before!=after)return 4;IOObjectRelease(backing);
    io_connect_t invalid=0;if(IOServiceOpen(service,mach_task_self(),1,&invalid)!=kIOReturnUnsupported||invalid)return 5;
    if(IOConnectCallMethod(connection,0xffffffff,NULL,0,NULL,0,NULL,NULL,NULL,NULL)!=kIOReturnUnsupported)return 6;
    invalid=0;if(IOServiceOpen(service,MACH_PORT_NULL,0,&invalid)!=kIOReturnNotPermitted||invalid)return 8;
    if(IOObjectRetain(connection)||IOObjectRetain(connection))return 14;
    if(IOServiceClose(connection)||IOServiceClose(connection)!=kIOReturnNotOpen)return 9;
    backing=0;if(IOConnectGetService(connection,&backing)!=kIOReturnNotOpen||backing)return 10;
    if(IOConnectCallMethod(connection,0xffffffff,NULL,0,NULL,0,NULL,NULL,NULL,NULL)!=kIOReturnNotOpen)return 11;
    if(IOConnectGetService(second,&backing)||!backing)return 12;IOObjectRelease(backing);
    if(IOServiceClose(second))return 13;IOObjectRelease(connection);
   }IOObjectRelease(service);
   if(!status&&connection){puts("IOSURFACE_ROOT_REAL_USER_CLIENT_OPEN_NATIVE_OK");return 0;}
  }
 }
 return 1;
}
