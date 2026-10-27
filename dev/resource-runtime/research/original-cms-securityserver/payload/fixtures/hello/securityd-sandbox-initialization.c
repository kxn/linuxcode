#include <stdint.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int sandbox_init_with_parameters(const char *,uint64_t,const char *const *,char **);
int main(void){
    setbuf(stdout,NULL);Dl_info info={0};
    if(!dladdr((void*)sandbox_init_with_parameters,&info))return 2;
    printf("SECURITYD_SANDBOX_PROVIDER %s\n",info.dli_fname);
    const char *parameters[]={"LEGACY_TOKENS_ENABLED","NO",NULL};char *error=NULL;
    errno=0;int status=sandbox_init_with_parameters("com.apple.securityd",1,parameters,&error);int saved=errno;
    printf("SECURITYD_SANDBOX_INITIALIZATION_STATUS %d ERRNO %d ERROR %s\n",status,saved,error?error:"(none)");
    int observed=status==-1&&saved==ENOTSUP&&error&&strstr(error,"not implemented");
    free(error);return observed?0:1;
}
