#include <libproc.h>
#include <sys/proc_info.h>
#include <sys/wait.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
static unsigned checks;
static pid_t child=-1;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"PROC_LISTPIDS_FAIL line=%d errno=%d\n",__LINE__,errno);if(child>0)kill(child,SIGKILL);return 1;}checks++;}while(0)
static int contains(const pid_t *p,int bytes,pid_t value){for(int i=0;i<bytes/(int)sizeof(*p);i++)if(p[i]==value)return 1;return 0;}
int main(void)
{
    setbuf(stdout,NULL);int capacity=proc_listpids(PROC_ALL_PIDS,0,NULL,0);CHECK(capacity>=21*sizeof(pid_t) && !(capacity%sizeof(pid_t)));
    pid_t *pids=malloc(capacity+32);CHECK(pids);memset(pids,0xa5,capacity+32);
    int bytes=proc_listpids(PROC_ALL_PIDS,0,pids,capacity);CHECK(bytes>0 && bytes<=capacity && !(bytes%sizeof(pid_t)));
    CHECK(contains(pids,bytes,getpid()) && contains(pids,bytes,getppid()));
    int guards=1;for(int i=capacity;i<capacity+32;i++)guards&=((unsigned char*)pids)[i]==0xa5;CHECK(guards);
    unsigned char tiny[12];memset(tiny,0xa5,sizeof(tiny));errno=0;CHECK(proc_listpids(PROC_ALL_PIDS,0,tiny+1,3)==0 && errno==ENOMEM);CHECK(tiny[0]==0xa5 && tiny[1]==0xa5 && tiny[4]==0xa5);
    CHECK(proc_listpids(PROC_ALL_PIDS,0,tiny+1,6)==sizeof(pid_t));CHECK(tiny[0]==0xa5 && tiny[5]==0xa5 && tiny[6]==0xa5 && tiny[7]==0xa5);
    errno=0;CHECK(proc_listpids(0,0,pids,capacity)==0 && errno==EINVAL);
    int control[2];CHECK(pipe(control)==0);child=fork();CHECK(child>=0);
    if(!child){close(control[1]);char b;while(read(control[0],&b,1)<0 && errno==EINTR){} _exit(0);}
    close(control[0]);CHECK(setpgid(child,child)==0);
    bytes=proc_listpids(PROC_ALL_PIDS,0,pids,capacity);CHECK(contains(pids,bytes,child) && contains(pids,bytes,getpid()));
    bytes=proc_listpids(PROC_PPID_ONLY,getpid(),pids,capacity);CHECK(contains(pids,bytes,child) && !contains(pids,bytes,getpid()));
    bytes=proc_listpids(PROC_PGRP_ONLY,child,pids,capacity);CHECK(contains(pids,bytes,child) && !contains(pids,bytes,getpid()));
    bytes=proc_listpids(PROC_PGRP_ONLY,getpgrp(),pids,capacity);CHECK(contains(pids,bytes,getpid()) && !contains(pids,bytes,child));
    bytes=proc_listpids(PROC_UID_ONLY,geteuid(),pids,capacity);CHECK(contains(pids,bytes,getpid()) && contains(pids,bytes,child));
    bytes=proc_listpids(PROC_RUID_ONLY,getuid(),pids,capacity);CHECK(contains(pids,bytes,getpid()) && contains(pids,bytes,child));
    CHECK(proc_listpids(PROC_UID_ONLY,UINT32_MAX,pids,capacity)==0);
    CHECK(proc_listpids(PROC_PPID_ONLY,UINT32_MAX,NULL,0)>=21*sizeof(pid_t));
    close(control[1]);int status;CHECK(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    bytes=proc_listpids(PROC_PPID_ONLY,getpid(),pids,capacity);CHECK(!contains(pids,bytes,child));child=-1;
    free(pids);printf("PROC_LISTPIDS_CHECKS %u\n",checks);puts("PROC_LISTPIDS_REAL_NAMESPACE_FAMILY_GROUP_UID_AND_BUFFER_ABI_OK");return 0;
}
