#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
static pthread_mutex_t *queue_mutex;
static int locked, release_lock;
static void *hold_queue_lock(void *unused) {
    if(pthread_mutex_lock(queue_mutex))abort();
    __atomic_store_n(&locked,1,__ATOMIC_RELEASE);
    while(!__atomic_load_n(&release_lock,__ATOMIC_ACQUIRE))usleep(1000);
    if(pthread_mutex_unlock(queue_mutex))abort();
    return NULL;
}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"KQUEUE_SPAWN_CHECK_FAILED line=%d errno=%d\n",__LINE__,errno);return 1;}}while(0)
int main(int argc,char **argv) {
    static const char message[]="source-owned queue fork reset\n";
    if(argc==2&&!strcmp(argv[1],"--child"))return write(1,message,sizeof(message)-1)==sizeof(message)-1?0:2;
    CHECK(argc==2);setbuf(stdout,NULL);alarm(8);
    void *kernel=dlopen("/usr/lib/system/libsystem_kernel.dylib",RTLD_LAZY|RTLD_LOCAL);CHECK(kernel);
    int (*create_queue)(void)=dlsym(kernel,"kqueue_impl");
    int (*close_queue)(int)=dlsym(kernel,"kqueue_close");CHECK(create_queue&&close_queue);
    Dl_info provider;CHECK(dladdr((void*)create_queue,&provider));
    CHECK(strstr(provider.dli_fname,"libsystem_kernel.dylib"));
    intptr_t delta=(intptr_t)strtoll(argv[1],NULL,0);
    queue_mutex=(pthread_mutex_t*)((uintptr_t)(void*)create_queue+delta);
    int queue=create_queue();CHECK(queue>=0);
    pthread_t holder;CHECK(!pthread_create(&holder,NULL,hold_queue_lock,NULL));
    while(!__atomic_load_n(&locked,__ATOMIC_ACQUIRE))usleep(1000);
    int pipefd[2];CHECK(!pipe(pipefd));
    posix_spawn_file_actions_t actions;CHECK(!posix_spawn_file_actions_init(&actions));
    CHECK(!posix_spawn_file_actions_adddup2(&actions,pipefd[1],STDOUT_FILENO));
    CHECK(!posix_spawn_file_actions_addclose(&actions,pipefd[0]));
    CHECK(!posix_spawn_file_actions_addclose(&actions,pipefd[1]));
    char *child_argv[]={argv[0],"--child",NULL};pid_t child=-1;
    printf("KQUEUE_SPAWN_FORK_RESET_BEGIN provider=%s\n",provider.dli_fname);
    int status=posix_spawn(&child,argv[0],&actions,NULL,child_argv,environ);
    __atomic_store_n(&release_lock,1,__ATOMIC_RELEASE);
    CHECK(!pthread_join(holder,NULL));CHECK(!status&&child>0);
    CHECK(!posix_spawn_file_actions_destroy(&actions));CHECK(!close(pipefd[1]));
    int result=-1;CHECK(waitpid(child,&result,0)==child);CHECK(WIFEXITED(result)&&WEXITSTATUS(result)==0);
    char actual[128];ssize_t count=read(pipefd[0],actual,sizeof actual);
    CHECK(count==sizeof(message)-1&&!memcmp(actual,message,count));CHECK(!close(pipefd[0]));
    /* Child cleanup must not discard or close the parent's independent queue. */
    CHECK(close_queue(queue)==1);alarm(0);
    puts("KQUEUE_SPAWN_FORK_RESET_OK");return 0;
}
