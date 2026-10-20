#include <dlfcn.h>
#include <objc/runtime.h>
#include <objc/message.h>
#include <stdio.h>
static id send0(id o,const char *s){return ((id(*)(id,SEL))objc_msgSend)(o,sel_registerName(s));}
static id str(const char *s){return ((id(*)(id,SEL,const char*))objc_msgSend)((id)objc_getClass("NSString"),sel_registerName("stringWithUTF8String:"),s);}
static void text(id o,const char *label){id s=send0(o,"description");const char *p=((const char*(*)(id,SEL))objc_msgSend)(s,sel_registerName("UTF8String"));printf("DIRECTORY_COPY_%s %s\n",label,p?p:"nil");}
int main(int argc,char **argv){
 if(argc!=3)return 10;setvbuf(stdout,NULL,_IOLBF,0);
 if(!dlopen("/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation",RTLD_LAZY|RTLD_GLOBAL)){printf("FOUNDATION_LOAD_FAILED %s\n",dlerror());return 11;}
 id manager=send0((id)objc_getClass("NSFileManager"),"defaultManager");id error=0;
 unsigned char ok=((unsigned char(*)(id,SEL,id,id,id*))objc_msgSend)(manager,sel_registerName("copyItemAtPath:toPath:error:"),str(argv[1]),str(argv[2]),&error);
 printf("DIRECTORY_COPY_RESULT %u\n",ok);
 for(unsigned depth=0;error && depth<5;depth++){
  printf("DIRECTORY_COPY_ERROR_DEPTH %u\n",depth);text(error,"ERROR");id info=send0(error,"userInfo");text(info,"USER_INFO");
  id path=((id(*)(id,SEL,id))objc_msgSend)(info,sel_registerName("objectForKey:"),str("NSFilePath"));text(path,"ERROR_PATH");
  error=((id(*)(id,SEL,id))objc_msgSend)(info,sel_registerName("objectForKey:"),str("NSUnderlyingError"));
 }
 return ok?0:12;
}
