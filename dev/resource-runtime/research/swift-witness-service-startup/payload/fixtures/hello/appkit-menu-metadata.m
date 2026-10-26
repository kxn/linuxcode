#import <Foundation/Foundation.h>
#import <objc/message.h>
#include <dlfcn.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 if(argc<2 || argc>3)return 2;
 @autoreleasepool {
  if(!dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL)){fprintf(stderr,"MENU_LOAD_ERROR %s\n",dlerror());return 3;}
  Class cls=NSClassFromString(@"NSMenu");if(!cls)return 4;
  puts("APPKIT_MENU_BEFORE_INIT");fflush(stdout);
  if(argc==3 && !strcmp(argv[2],"--pause-for-debugger"))raise(SIGSTOP);
  id allocated=((id(*)(id,SEL))objc_msgSend)(cls,sel_registerName("alloc"));
  id menu=((id(*)(id,SEL,id))objc_msgSend)(allocated,sel_registerName("initWithTitle:"),@"Linuxcode metadata probe");
  if(!menu)return 5;
  NSString *title=((id(*)(id,SEL))objc_msgSend)(menu,sel_registerName("title"));
  printf("APPKIT_MENU_TITLE %s\n",[title UTF8String]);
  if(![title isEqualToString:@"Linuxcode metadata probe"])return 6;
  [menu release];puts("APPKIT_MENU_METADATA_NATIVE_OK");return 0;
 }
}
