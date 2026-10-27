#include <errno.h>
#include <mach/machine.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#define CHECK(v) do{if(!(v)){fprintf(stderr,"NULLENV_FAIL line=%d errno=%d\n",__LINE__,errno);exit(1);}}while(0)
extern char** environ;
int main(int argc,char** argv) {
 alarm(35);setbuf(stdout,NULL);
 if(argc==3&&!strcmp(argv[1],"--child")) {
  const char* value=getenv("NULLENV_SENTINEL");
  CHECK(atoi(argv[2]) ? value&&!strcmp(value,"parent-must-not-leak") : !value);
  if(!atoi(argv[2])){CHECK(!getenv("DYLD_LIBRARY_PATH"));CHECK(!getenv("DYLD_FRAMEWORK_PATH"));}
  return 0;
 }
 CHECK(setenv("NULLENV_SENTINEL","parent-must-not-leak",1)==0);
 for(int mode=0;mode<3;mode++)for(int vector=0;vector<3;vector++) {
  char* empty[]={NULL};char** env=vector==0?NULL:vector==1?empty:environ;
  char* args[]={argv[0],"--child",vector==2?"1":"0",NULL};pid_t child;
  if(mode==0){child=fork();CHECK(child>=0);if(!child){execve(argv[0],args,env);_exit(127);}}
  else {
   posix_spawnattr_t attr;CHECK(posix_spawnattr_init(&attr)==0);
   if(mode==2){cpu_type_t arch=CPU_TYPE_X86_64;size_t count=0;CHECK(posix_spawnattr_setbinpref_np(&attr,1,&arch,&count)==0);CHECK(count==1);}
   CHECK(posix_spawn(&child,argv[0],NULL,&attr,args,env)==0);CHECK(posix_spawnattr_destroy(&attr)==0);
  }
  int status;CHECK(waitpid(child,&status,0)==child);CHECK(WIFEXITED(status)&&WEXITSTATUS(status)==0);
  CHECK(!strcmp(getenv("NULLENV_SENTINEL"),"parent-must-not-leak"));CHECK(empty[0]==NULL);
 }
 puts("NULLENV_EXEC_SPAWN_BINPREF_NULL_EMPTY_EXPLICIT_AND_PARENT_ISOLATION_OK");return 0;
}
