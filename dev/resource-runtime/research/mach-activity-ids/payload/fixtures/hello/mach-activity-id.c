#include <dlfcn.h>
#include <mach/mach.h>
#include <pthread.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#define CHECK(x) do{if(!(x)){printf("ACTIVITY_FAILED line=%d %s\n",__LINE__,#x);return 1;}}while(0)
struct range{uint64_t start;uint32_t count,reserved;};
typedef kern_return_t(*allocate_t)(mach_port_t,int,uint64_t*);
static allocate_t allocate_id;static struct range ranges[770];static unsigned errors;
extern char** environ;
static int fill(struct range* output,unsigned count){for(unsigned i=0;i<count;i++){output[i].count=i%16+1;if(allocate_id(mach_task_self(),output[i].count,&output[i].start)!=0||!output[i].start)return 0;}return 1;}
static void* worker(void* p){if(!fill(ranges+(uintptr_t)p*64,64))__atomic_add_fetch(&errors,1,__ATOMIC_RELAXED);return 0;}
static int compare(const void* a,const void* b){uint64_t x=((const struct range*)a)->start,y=((const struct range*)b)->start;return (x>y)-(x<y);}
int main(int argc,char** argv){
 allocate_id=dlsym(RTLD_DEFAULT,"mach_generate_activity_id");CHECK(allocate_id);
 if(argc==2&&!strcmp(argv[1],"--child")){struct range child[128]={0};CHECK(fill(child,128));const char* at=(const char*)child;unsigned left=sizeof child;while(left){ssize_t n=write(STDOUT_FILENO,at,left);CHECK(n>0);at+=n;left-=n;}return 0;}
 setbuf(stdout,NULL);uint64_t sentinel=0xabcdefabcdef1234ull;CHECK(allocate_id(mach_task_self(),0,&sentinel)==KERN_INVALID_ARGUMENT&&sentinel==0xabcdefabcdef1234ull);CHECK(allocate_id(mach_task_self(),-1,&sentinel)==KERN_INVALID_ARGUMENT);CHECK(allocate_id(mach_task_self(),17,&sentinel)==KERN_INVALID_ARGUMENT);CHECK(allocate_id(mach_task_self(),1,(void*)1)!=KERN_SUCCESS);
 CHECK(fill(ranges+768,2));
 int channel[2][2];pid_t children[2];
 for(unsigned c=0;c<2;c++){
  CHECK(pipe(channel[c])==0);posix_spawn_file_actions_t actions;CHECK(posix_spawn_file_actions_init(&actions)==0);CHECK(posix_spawn_file_actions_addclose(&actions,channel[c][0])==0);CHECK(posix_spawn_file_actions_adddup2(&actions,channel[c][1],STDOUT_FILENO)==0);CHECK(posix_spawn_file_actions_addclose(&actions,channel[c][1])==0);char* args[]={argv[0],"--child",NULL};CHECK(posix_spawn(&children[c],argv[0],&actions,NULL,args,environ)==0);CHECK(posix_spawn_file_actions_destroy(&actions)==0);CHECK(close(channel[c][1])==0);
 }
 pthread_t threads[8];for(uintptr_t i=0;i<8;i++)CHECK(pthread_create(&threads[i],NULL,worker,(void*)i)==0);for(unsigned i=0;i<8;i++)CHECK(pthread_join(threads[i],NULL)==0);CHECK(!errors);
 for(unsigned c=0;c<2;c++){
  char* at=(char*)(ranges+512+c*128);unsigned left=128*sizeof(struct range);while(left){ssize_t n=read(channel[c][0],at,left);CHECK(n>0);at+=n;left-=n;}CHECK(close(channel[c][0])==0);int status;CHECK(waitpid(children[c],&status,0)==children[c]&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
 }
 qsort(ranges,770,sizeof ranges[0],compare);uint64_t total=0;
 for(unsigned i=0;i<770;i++){CHECK(ranges[i].start&&ranges[i].count>=1&&ranges[i].count<=16&&!ranges[i].reserved);if(i)CHECK(ranges[i-1].start+ranges[i-1].count<=ranges[i].start);total+=ranges[i].count;}
 printf("MACH_ACTIVITY_REAL_SERVER_WIDE_NONOVERLAPPING_RANGES_OK threads=8 exec_children=2 ranges=770 ids=%llu\n",total);return 0;
}
