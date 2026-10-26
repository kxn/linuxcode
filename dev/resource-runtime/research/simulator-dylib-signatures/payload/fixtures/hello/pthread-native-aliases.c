#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#define CHECK(x) do {if(!(x)){printf("failed %d %s\n",__LINE__,#x);return 1;}}while(0)
static void (*yield_alias)(void);
static void* worker(void* arg) {for(int i=0;i<32;++i)yield_alias();return arg;}
int main(void) {
 void* h=dlopen("/usr/lib/system/libsystem_pthread.dylib",RTLD_LAZY|RTLD_LOCAL);CHECK(h);
 void* sched=dlsym(h,"sched_yield");yield_alias=dlsym(h,"pthread_yield_np");CHECK(sched && (void*)yield_alias==sched);CHECK(dlsym(h,"cthread_yield")==sched);
 int (*threaded)(void)=dlsym(h,"pthread_is_threaded_np");int (*threaded_alias)(void)=dlsym(h,"_pthread_is_threaded");CHECK(threaded && threaded==threaded_alias);CHECK(threaded()==threaded_alias());
 for(int i=0;i<32;++i)yield_alias();pthread_t t;void* result=0;CHECK(!pthread_create(&t,0,worker,(void*)83));CHECK(!pthread_join(t,&result));CHECK(result==(void*)83);CHECK(threaded_alias());
 puts("PTHREAD_UPSTREAM_ALIASES_EXACT_TARGETS_AND_REAL_THREADS_NATIVE_OK");return 0;
}
