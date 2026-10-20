#include <dlfcn.h>
#include <objc/runtime.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 if(argc!=3)return 10;setvbuf(stdout,NULL,_IOLBF,0);
 void *library=dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL);if(!library){printf("AUTOMATOR_DLOPEN_FAILED %s\n",dlerror());return 11;}
 Class actual=dlsym(library,"OBJC_CLASS_$_AMPathPopUpButton");if(!actual)return 13;
 Method method=class_getInstanceMethod(actual,sel_registerName("encodeWithCoder:"));
 const char *types=method?method_getTypeEncoding(method):NULL;
 if(!types){puts("AUTOMATOR_REQUIRED_CODER_METHOD_MISSING");return 12;}
 printf("AUTOMATOR_CODER_METHOD %s\n",types);
 Dl_info owner;if(!dladdr(actual,&owner))return 13;printf("AUTOMATOR_CLASS_PROVIDER %s\n",owner.dli_fname);
 if(!strstr(owner.dli_fname,argv[1]))return 14;
 if(strcmp(class_getName(actual),argv[2]))return 15;
 if(actual!=objc_getClass("AMPathPopUpButton") || class_isMetaClass(actual))return 16;
 int variable=0,popup=0,depth=0;
 for(Class c=actual;c && depth<24;c=class_getSuperclass(c),++depth){const char *name=class_getName(c);printf("AUTOMATOR_SUPERCLASS %s\n",name);if(!strcmp(name,"_AMVariablePopUpButton"))variable=1;if(!strcmp(name,"NSPopUpButton"))popup=1;}
 if(!variable || !popup || class_getInstanceSize(actual)<=sizeof(void*))return 17;
 puts("ORIGINAL_AUTOMATOR_CLASS_SUPERCHAIN_AND_CODER_METHOD_OK");return 0;
}
