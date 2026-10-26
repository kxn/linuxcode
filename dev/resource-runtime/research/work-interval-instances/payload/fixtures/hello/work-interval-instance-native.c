#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#define CHECK(x) do {if(!(x)){printf("failed %d: %s errno=%d\n",__LINE__,#x,errno);return 1;}}while(0)
int main(void) {
    void* lib=dlopen("/usr/lib/system/libsystem_kernel.dylib",RTLD_LAZY|RTLD_LOCAL);CHECK(lib);
    const char* names[]={"alloc","free","clear","set_start","set_finish","set_deadline","set_complexity","get_id","get_start","get_finish","get_deadline","get_complexity","get_telemetry_data","start","update","finish"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i){char name[100];snprintf(name,sizeof(name),"work_interval_instance_%s",names[i]);CHECK(dlsym(lib,name));}
    int (*create)(void**,uint32_t)=dlsym(lib,"work_interval_create");CHECK(create);errno=0;CHECK(create(0,0)==-1 && errno==EINVAL);
    void* wi=0;errno=0;CHECK(create(&wi,5)==-1);CHECK(errno==ENOSYS || errno==ENOTSUP);CHECK(!wi);puts("WORK_INTERVAL_KERNEL_CAPABILITY_FAILURE_PROPAGATED");
    const char* checks[]={"work_interval_instance_start","work_interval_instance_update","work_interval_instance_finish"};
    for(unsigned i=0;i<3;++i){int(*f)(void*)=dlsym(lib,checks[i]);errno=0;CHECK(f(0)==-1 && errno==EINVAL);}
    puts("WORK_INTERVAL_INSTANCE_EXPORTS_AND_REAL_BACKEND_ERRORS_NATIVE_OK");return 0;
}
