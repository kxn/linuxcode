#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
int main(int argc,char** argv) {
 if(argc<2)return 2;
 /* Leave time for the host debugger to attach before the one target spawn. */
 int offset=!strcmp(argv[1],"--empty-env")?2:1;if(argc<=offset)return 2;
 sleep(3);pid_t child;int error=posix_spawn(&child,argv[offset],NULL,NULL,argv+offset,offset==2?NULL:environ);
 if(error){fprintf(stderr,"DIAGNOSTIC_SPAWN_ERROR %d\n",error);return 2;}
 int status;while(waitpid(child,&status,0)<0){}
 if(WIFSIGNALED(status)){printf("DIAGNOSTIC_CHILD_SIGNAL %d\n",WTERMSIG(status));return 128+WTERMSIG(status);}
 return WIFEXITED(status)?WEXITSTATUS(status):2;
}
