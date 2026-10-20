#include <dlfcn.h>
#include <objc/runtime.h>
#include <stdint.h>
#include <stdio.h>
int main(int argc,char **argv) {
 if(argc!=2)return 10;setvbuf(stdout,NULL,_IOLBF,0);
 void *library=dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL);
 if(!library){printf("COCOA_PLUGIN_DLOPEN_FAILED %s\n",dlerror());return 11;}
 Class plugin=objc_getClass("IBCocoaPlugin");Dl_info image;if(!plugin||!dladdr(plugin,&image))return 12;
 printf("COCOA_PLUGIN_PROVIDER %s\n",image.dli_fname);
 uintptr_t base=(uintptr_t)image.dli_fbase;
 Class reference=*(Class*)(base+0x2caa40),category=*(Class*)(base+0x271680+8),registered=objc_getClass("AMPathPopUpButton");
 Class classes[]={reference,category,registered};const char *labels[]={"classref","category","registered"};
 for(unsigned i=0;i<3;i++) {
  Class cls=classes[i];printf("COCOA_CATEGORY_CLASS %s %p %s\n",labels[i],cls,cls?class_getName(cls):"nil");
  if(!cls)continue;
  Dl_info provider;if(dladdr(cls,&provider))printf("COCOA_CATEGORY_PROVIDER %s %s\n",labels[i],provider.dli_fname);
  const char *names[]={"encodeWithCoder:","ibSwizzledEncodeWithCoder:","ibLocalAttributeKeyPaths","ibDesignModeEncodeWithCoderCount"};
  for(unsigned j=0;j<4;j++) {
   Method m=class_getInstanceMethod(cls,sel_registerName(names[j]));const char *type=m?method_getTypeEncoding(m):NULL;
   printf("COCOA_CATEGORY_METHOD %s %s %p %s\n",labels[i],names[j],m,type?type:"nil");
  }
 }
 puts("COCOA_CATEGORY_DIAGNOSTIC_COMPLETE");return 0;
}
