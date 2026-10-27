#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
static pid_t child = -1;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"WAITID_FAIL line=%d errno=%d\n",__LINE__,errno); if(child>0)kill(child,SIGKILL); return 1; } checks++; } while(0)
static int wait_event(int number, idtype_t type, pid_t id, siginfo_t *info, int options)
{
    return (int)syscall(number,type,id,info,options);
}
int main(void)
{
    setbuf(stdout,NULL);
    siginfo_t info, before;
    memset(&info,0x55,sizeof(info)); before=info;
    errno=0; CHECK(wait_event(SYS_waitid_nocancel,P_ALL,0,&info,WEXITED|WNOHANG)==-1 && errno==ECHILD);
    CHECK(memcmp(&info,&before,sizeof(info))==0);
    errno=0; CHECK(wait_event(SYS_waitid_nocancel,P_ALL,0,&info,0)==-1 && errno==EINVAL);
    errno=0; CHECK(wait_event(SYS_waitid_nocancel,P_ALL,0,&info,WEXITED|0x40000000)==-1 && errno==EINVAL);
    int fds[2]; CHECK(pipe(fds)==0);
    child=fork(); CHECK(child>=0);
    if(child==0){ close(fds[1]); char value; while(read(fds[0],&value,1)<0 && errno==EINTR){} _exit(37); }
    close(fds[0]);
    CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WEXITED|WNOHANG)==0);
    CHECK(memcmp(&info,&before,sizeof(info))==0);
    CHECK(kill(child,SIGSTOP)==0);
    CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WSTOPPED)==0);
    CHECK(info.si_pid==child && info.si_signo==SIGCHLD && info.si_code==CLD_STOPPED && info.si_status==SIGSTOP);
    CHECK(kill(child,SIGCONT)==0);
    CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WCONTINUED)==0);
    CHECK(info.si_pid==child && info.si_code==CLD_CONTINUED && info.si_status==SIGCONT);
    close(fds[1]);
    CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WEXITED|WNOWAIT)==0);
    CHECK(info.si_pid==child && info.si_code==CLD_EXITED && info.si_status==37 && info.si_uid==getuid());
    CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WEXITED|WNOWAIT)==0 && info.si_status==37);
    CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WEXITED)==0 && info.si_status==37);
    errno=0; CHECK(wait_event(SYS_waitid_nocancel,P_PID,child,&info,WEXITED|WNOHANG)==-1 && errno==ECHILD); child=-1;
    child=fork(); CHECK(child>=0);
    if(child==0){ for(;;)pause(); }
    CHECK(kill(child,SIGUSR1)==0);
    CHECK(wait_event(SYS_waitid,P_ALL,0,&info,WEXITED)==0);
    CHECK(info.si_pid==child && info.si_signo==SIGCHLD && info.si_code==CLD_KILLED && info.si_status==SIGUSR1); child=-1;
    child=fork(); CHECK(child>=0);
    if(child==0){ for(;;)pause(); }
    CHECK(setpgid(child,child)==0 && kill(child,SIGKILL)==0);
    CHECK(wait_event(SYS_waitid_nocancel,P_PGID,child,&info,WEXITED)==0);
    CHECK(info.si_pid==child && info.si_code==CLD_KILLED && info.si_status==SIGKILL); child=-1;
    printf("WAITID_CHECKS %u\n",checks); puts("WAITID_CHILD_EVENTS_VERIFIED"); return 0;
}
