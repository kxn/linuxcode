#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../../vendor/darling/src/startup/mldr/initial-stack.h"
int main(int argc,char** argv) {
 assert(argc==3&&!strcmp(argv[1],"literal space = UTF8 值")&&!strcmp(argv[2],"unchanged"));
 const char* recorded=getenv("MLDR_INITIAL_STACK_TEST_ADDRESS");uintptr_t address;
 if(!recorded) {
  address=(uintptr_t)(argv-1)&~(uintptr_t)4095;
  char value[64];snprintf(value,sizeof(value),"%lx",(unsigned long)address);assert(setenv("MLDR_INITIAL_STACK_TEST_ADDRESS",value,1)==0);
  snprintf(value,sizeof(value),"%d",getpid());assert(setenv("MLDR_INITIAL_STACK_TEST_PID",value,1)==0);
  int pipefd[2];assert(pipe(pipefd)==0);assert(write(pipefd[1],"x",1)==1);close(pipefd[1]);
  snprintf(value,sizeof(value),"%d",pipefd[0]);assert(setenv("MLDR_INITIAL_STACK_TEST_FD",value,1)==0);
  assert(setenv("MLDR_INITIAL_STACK_TEST_VALUE","literal $() `text`; UTF8=值",1)==0);
  assert(mldr_initial_stack_is_live((uintptr_t)(argv-1),address,4096)==1);
  mldr_prepare_initial_stack(argv,address,4096);
  assert(!"Expected a real self-exec into another initial stack layout");
 }
 address=strtoul(recorded,NULL,16);
 assert(getpid()==atoi(getenv("MLDR_INITIAL_STACK_TEST_PID")));
 assert(!strcmp(getenv("MLDR_INITIAL_STACK_TEST_VALUE"),"literal $() `text`; UTF8=值"));
 assert(mldr_prepare_initial_stack(argv,address,4096)==0);
 char byte=0;int fd=atoi(getenv("MLDR_INITIAL_STACK_TEST_FD"));assert(read(fd,&byte,1)==1&&byte=='x');close(fd);
 unsigned attempts=atoi(getenv("__mldr_stack_attempt"));assert(attempts>0&&attempts<=16);
 uintptr_t initial=(uintptr_t)(argv-1);assert(mldr_initial_stack_is_live(initial,(initial&~(uintptr_t)4095)-4096,4096)==0);
 assert(setenv("__mldr_stack_attempt","16",1)==0);errno=0;
 assert(mldr_prepare_initial_stack(argv,initial&~(uintptr_t)4095,4096)==-1&&errno==EADDRNOTAVAIL);
 puts("MLDR_INITIAL_LIVE_STACK_REAL_SELF_EXEC_PID_ARGV_ENV_FD_AND_RETRY_BOUND_OK");
}
