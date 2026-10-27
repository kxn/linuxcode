#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int main(void){
    setbuf(stdout,NULL);char temporary[]="/tmp/.dotnet-probe.XXXXXX";const char *destination="/tmp/.dotnet-probe-target";
    if(!mkdtemp(temporary)||chmod(temporary,0777))return 2;
    struct stat parent;stat("/tmp",&parent);printf("SHARED_RENAME_BEGIN pid=%d parent_dev=%llu parent_ino=%llu\n",getpid(),(unsigned long long)parent.st_dev,(unsigned long long)parent.st_ino);
    sleep(4);errno=0;int result=rename(temporary,destination);int error=errno;
    printf("SHARED_RENAME_RESULT result=%d errno=%d\n",result,error);
    if(!result)rmdir(destination);else rmdir(temporary);
    return result?1:0;
}
