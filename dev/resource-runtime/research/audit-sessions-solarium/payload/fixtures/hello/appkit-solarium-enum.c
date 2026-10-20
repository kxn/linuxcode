#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
int main(int argc,char **argv) {
    if(argc!=3)return 10;
    void *library=dlopen(argv[1],RTLD_LAZY|RTLD_GLOBAL);
    if(!library){printf("SOLARIUM_DLOPEN_FAILED %s\n",dlerror());return 11;}
    unsigned char (*enabled)(void)=dlsym(library,"NSSolariumEnabled");Dl_info owner;
    if(!enabled){printf("SOLARIUM_SYMBOL_FAILED %s\n",dlerror());return 14;}
    if(!dladdr((void*)enabled,&owner))return 14;
    printf("SOLARIUM_PROVIDER %s\n",owner.dli_fname);
    if(!strstr(owner.dli_fname,argv[1]))return 14;
    const uint32_t *const *slot=(const uint32_t *const *)((uintptr_t)owner.dli_fbase+0x39289cb0);
    if(!*slot){puts("SOLARIUM_ENUM_INDEX_MISSING");return 12;}
    printf("SOLARIUM_ENUM_VALUE %u provider=%s\n",**slot,owner.dli_fname);
    if(**slot!=(uint32_t)strtoul(argv[2],NULL,10))return 15;
    unsigned char result=enabled();if(result>1)return 16;
    for(int i=0;i<8;++i)if(enabled()!=result)return 17;
    pid_t child=fork();if(child<0)return 18;
    if(!child){signal(SIGSEGV,SIG_DFL);*(volatile uint32_t*)*slot=99;_exit(19);}
    int status;if(waitpid(child,&status,0)!=child || !WIFSIGNALED(status) || WTERMSIG(status)!=SIGSEGV)return 20;
    if(**slot!=1)return 21;
    printf("ORIGINAL_NSSOLARIUM_ENABLED_ENUM_AND_READONLY_OK %u\n",result);return 0;
}
