#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/message.h>
#include <dlfcn.h>
#include <stdio.h>
static const char *text(NSString *s) {return s ? [s UTF8String] : "(nil)";}
int main(int argc,char **argv) {
 if(argc!=2)return 2;
 @autoreleasepool {
  if(!dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL)){fprintf(stderr,"LOAD_ERROR %s\n",dlerror());return 3;}
  Class cls=NSClassFromString(@"DIError");if(!cls)return 4;
  NSBundle *bundle=[NSBundle bundleForClass:cls];
  printf("LOCALIZATION_BUNDLE path=%s id=%s\n",text(bundle.bundlePath),text(bundle.bundleIdentifier));
  printf("LOCALIZATION_RESOURCE %s\n",text([bundle pathForResource:@"Localizable" ofType:@"strings" inDirectory:nil forLocalization:@"en"]));
  NSString *key=@"Disk image operation failed with error code %d";
  NSString *translated=[bundle localizedStringForKey:key value:key table:nil];
  printf("LOCALIZATION_BUNDLE_STRING %s\n",text(translated));
  NSURL *url=[NSURL fileURLWithPath:bundle.bundlePath];
  CFBundleRef cf=CFBundleCreate(kCFAllocatorDefault,(CFURLRef)url);
  CFStringRef direct=cf?CFBundleCopyLocalizedString(cf,(CFStringRef)key,(CFStringRef)key,NULL):NULL;
  printf("LOCALIZATION_CF_STRING %s\n",text((NSString *)direct));
  if(direct)CFRelease(direct);if(cf)CFRelease(cf);
  int failures=(!bundle || !bundle.bundleIdentifier || !translated);
  int codes[]={0,1,100,152,153,157,-1};
  for(unsigned i=0;i<sizeof(codes)/sizeof(codes[0]);++i) {
   @try {
    NSString *s=((id(*)(id,SEL,long long))objc_msgSend)(cls,sel_registerName("copyDefaultLocalizedStringForDIErrorCode:"),codes[i]);
    printf("LOCALIZATION_DI_ERROR code=%d value=%s\n",codes[i],text(s));
    if(codes[i]==153 && !s)++failures;[s release];
   } @catch(NSException *e) {
    printf("LOCALIZATION_EXCEPTION code=%d name=%s reason=%s\n",codes[i],text(e.name),text(e.reason));++failures;
   }
   fflush(stdout);
  }
  printf("LOCALIZATION_FAILURES %d\n",failures);
  return failures?1:0;
 }
}
