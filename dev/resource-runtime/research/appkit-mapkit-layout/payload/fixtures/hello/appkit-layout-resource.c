#include <dlfcn.h>
#include <objc/runtime.h>
#include <objc/message.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static id call0(id obj,const char *sel) {return ((id(*)(id,SEL))objc_msgSend)(obj,sel_registerName(sel));}
static id string(const char *s) {return ((id(*)(id,SEL,const char*))objc_msgSend)((id)objc_getClass("NSString"),sel_registerName("stringWithUTF8String:"),s);}
int main(int argc,char **argv) {
 if(argc!=4)return 10;setvbuf(stdout,NULL,_IOLBF,0);
 if(!dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL)){printf("APPKIT_DLOPEN_FAILED %s\n",dlerror());return 11;}
 Class theme=objc_getClass("NSUserInterfaceTheme");if(!theme)return 13;
 id bundle=((id(*)(id,SEL,Class))objc_msgSend)((id)objc_getClass("NSBundle"),sel_registerName("bundleForClass:"),theme);
 id path=((id(*)(id,SEL,id,id))objc_msgSend)(bundle,sel_registerName("pathForResource:ofType:"),string("AquaGuideRules"),string("plist"));
 if(!path){puts("APPKIT_LAYOUT_RESOURCE_MISSING");return 12;}
 const char *filename=((const char*(*)(id,SEL))objc_msgSend)(path,sel_registerName("UTF8String"));printf("APPKIT_LAYOUT_RESOURCE_PATH %s\n",filename);
 if(!strstr(filename,argv[2]))return 14;
 id data=((id(*)(id,SEL,id))objc_msgSend)((id)objc_getClass("NSData"),sel_registerName("dataWithContentsOfFile:"),path);
 unsigned long length=((unsigned long(*)(id,SEL))objc_msgSend)(data,sel_registerName("length"));printf("APPKIT_LAYOUT_RESOURCE_BYTES %lu\n",length);
 if(length!=strtoul(argv[3],NULL,10))return 15;
 id rules=((id(*)(id,SEL,id))objc_msgSend)((id)objc_getClass("NSDictionary"),sel_registerName("dictionaryWithContentsOfFile:"),path);
 unsigned long count=((unsigned long(*)(id,SEL))objc_msgSend)(rules,sel_registerName("count"));printf("APPKIT_LAYOUT_RULE_GROUPS %lu\n",count);if(!count)return 16;
 puts("ORIGINAL_APPKIT_LAYOUT_BUNDLE_LOOKUP_AND_PLIST_READ_OK");return 0;
}
