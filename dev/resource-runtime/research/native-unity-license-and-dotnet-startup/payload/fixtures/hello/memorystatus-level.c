#include <sys/types.h>
#include <sys/sysctl.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"MEMSTATUS_FAIL line=%d errno=%d\n",__LINE__,errno);return 1;}checks++;}while(0)
int main(int argc,char **argv){
    unsigned checks=0;setbuf(stdout,NULL);
    printf("GC_INIT_INPUTS pagesize=%ld cpus=%ld physical_pages=%ld\n",sysconf(29),sysconf(58),sysconf(200));
    size_t count=0;errno=0;int result=sysctlnametomib("kern.memorystatus_level",NULL,&count);
    printf("MEMSTATUS_NAME_SIZE result=%d errno=%d count=%zu\n",result,errno,count);
    if(argc>1&&!strcmp(argv[1],"missing")){CHECK(result==-1&&errno==ENOENT);puts("MEMSTATUS_MISSING_REPRODUCED");return 0;}
    CHECK(result==0&&count==2);int mib[2]={-1,-1};count=2;
    CHECK(sysctlnametomib("kern.memorystatus_level",mib,&count)==0&&count==2&&mib[0]==CTL_KERN);
    size_t size=0;CHECK(sysctl(mib,2,NULL,&size,NULL,0)==0&&size==sizeof(unsigned));
    unsigned level=UINT32_MAX;size=sizeof(level);CHECK(sysctl(mib,2,&level,&size,NULL,0)==0&&level<=100&&size==sizeof(level));
    printf("MEMSTATUS_LEVEL %u\n",level);
    unsigned named=UINT32_MAX;size=sizeof(named);CHECK(sysctlbyname("kern.memorystatus_level",&named,&size,NULL,0)==0&&named<=100);
    unsigned guard=0x12345678;size=sizeof(guard)-1;errno=0;CHECK(sysctl(mib,2,&guard,&size,NULL,0)==-1&&errno==ENOMEM&&guard==0x12345678&&size==0);
    unsigned replacement=17;size=sizeof(named);errno=0;CHECK(sysctl(mib,2,&named,&size,&replacement,sizeof(replacement))==-1&&errno==EPERM);
    errno=0;CHECK(sysctlbyname("kern.memorystatus_level",NULL,NULL,&replacement,sizeof(replacement))==-1&&errno==EPERM);
    puts("MEMSTATUS_READONLY_AND_BUFFER_ABI_OK");printf("MEMSTATUS_CHECKS %u\n",checks);return 0;
}
