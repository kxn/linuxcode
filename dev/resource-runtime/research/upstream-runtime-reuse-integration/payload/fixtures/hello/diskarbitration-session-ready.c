#include <DiskArbitration/DiskArbitration.h>
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <unistd.h>
int main(void) {
 Dl_info owner={0};dladdr((void*)DASessionCreate,&owner);
 fprintf(stderr,"DA_SESSION_READY_OWNER %s\n",owner.dli_fname);
 for(unsigned i=0;i<30;++i) {
  DASessionRef session=DASessionCreate(kCFAllocatorDefault);
  if(session){fprintf(stderr,"DA_SESSION_READY_NATIVE_OK type=%lu\n",(unsigned long)CFGetTypeID(session));CFRelease(session);return 0;}
  usleep(100000);
 }
 fprintf(stderr,"DA_SESSION_READY_NATIVE_FAILED\n");return 1;
}
