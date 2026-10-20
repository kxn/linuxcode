#include <dlfcn.h>
#include <objc/runtime.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 if(argc!=3)return 10;setvbuf(stdout,NULL,_IOLBF,0);
 void *library=dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL);if(!library){printf("MAPKIT_DLOPEN_FAILED %s\n",dlerror());return 11;}
 Class actual=dlsym(library,"OBJC_CLASS_$_MKLookAroundViewController");if(!actual){puts("MAPKIT_LOOKAROUND_CLASS_MISSING");return 12;}
 Dl_info owner;if(!dladdr((void *)actual,&owner))return 13;printf("MAPKIT_CLASS_PROVIDER %s\n",owner.dli_fname);
 if(!strstr(owner.dli_fname,argv[1]))return 14;
 if(strcmp(class_getName(actual),argv[2]))return 15;
 if(actual!=objc_getClass("MKLookAroundViewController") || class_isMetaClass(actual))return 16;
 int found=0,depth=0;for(Class c=actual;c && depth<24;c=class_getSuperclass(c),++depth){printf("MAPKIT_SUPERCLASS %s\n",class_getName(c));if(!strcmp(class_getName(c),"NSViewController"))found=1;}
 if(!found || class_getInstanceSize(actual)<=sizeof(void *))return 17;
 puts("ORIGINAL_MAPKIT_LOOKAROUND_CLASS_METADATA_AND_SUPERCHAIN_OK");return 0;
}
