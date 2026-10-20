#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
 setvbuf(stdout,NULL,_IOLBF,0);
 if(argc!=3)return 10;void *library=dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL);if(!library){printf("ANY_DLOPEN_FAILED %s\n",dlerror());return 11;}
 void *query=dlsym(library,"NSSolariumEnabled");Dl_info owner;if(!query || !dladdr(query,&owner) || !strstr(owner.dli_fname,argv[1]))return 14;
 void *const *slot=(void *const *)((uintptr_t)owner.dli_fbase+0x392ae880);
 if(!*slot){puts("ANY_POOL_REFERENCE_MISSING");return 12;}
 void *storage=dlsym(RTLD_DEFAULT,"$sypN");if(!storage || storage!=*slot)return 16;
 const uint64_t *metadata=(const uint64_t *)((const char *)storage+8);printf("ANY_METADATA_KIND %llu\n",(unsigned long long)*metadata);
 if(*metadata!=strtoull(argv[2],NULL,0))return 15;
 /* Generic Swift entry receives explicit metatype and generic metadata. */
 unsigned char (*isClass)(const void *,const void *)=dlsym(RTLD_DEFAULT,"_swift_isClassOrObjCExistentialType");if(!isClass)return 17;
 for(int i=0;i<32;++i)if(isClass(metadata,metadata)!=0)return 18;
 Dl_info real;if(!dladdr(storage,&real))return 19;printf("ANY_METADATA_PROVIDER %s\n",real.dli_fname);
 puts("ORIGINAL_SWIFT_ANY_BINDING_AND_TYPE_QUERY_OK");return 0;
}
