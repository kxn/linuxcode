/* Diagnostic only: submit the original service with a real NSArgumentDomain
 * preference. The bundle, executable, resource tool and SDK stay original. */
#include <launch.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char**argv) {
 assert(argc==2);
 const char*name="com.apple.CoreSimulator.CoreSimulatorService";
 launch_data_t job=launch_data_alloc(LAUNCH_DATA_DICTIONARY);
 launch_data_t args=launch_data_alloc(LAUNCH_DATA_ARRAY);
 launch_data_t services=launch_data_alloc(LAUNCH_DATA_DICTIONARY);
 launch_data_t env=launch_data_alloc(LAUNCH_DATA_DICTIONARY);
 launch_data_t request=launch_data_alloc(LAUNCH_DATA_DICTIONARY);
 assert(job && args && services && env && request);
 launch_data_dict_insert(job,launch_data_new_string(name),LAUNCH_JOBKEY_LABEL);
 launch_data_dict_insert(job,launch_data_new_string(argv[1]),LAUNCH_JOBKEY_PROGRAM);
 const char*arguments[]={argv[1],"-EnableVolumeManager","NO"};
 for(unsigned i=0;i<3;++i)assert(launch_data_array_set_index(args,launch_data_new_string(arguments[i]),i));
 launch_data_dict_insert(job,args,LAUNCH_JOBKEY_PROGRAMARGUMENTS);
 launch_data_dict_insert(job,launch_data_new_bool(1),LAUNCH_JOBKEY_ONDEMAND);
 launch_data_dict_insert(services,launch_data_new_bool(1),name);
 launch_data_dict_insert(job,services,LAUNCH_JOBKEY_MACHSERVICES);
 const char*keys[]={"DARLING_DYLD_OVERRIDE_EXECUTABLES","DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH","DARLING_DYLD_OVERRIDE_LIBRARY_PATH","DARLING_XPC_TRACE_LAUNCH_JOBS"};
 for(unsigned i=0;i<4;++i){const char*v=getenv(keys[i]);if(v)assert(launch_data_dict_insert(env,launch_data_new_string(v),keys[i]));}
 launch_data_dict_insert(job,env,LAUNCH_JOBKEY_ENVIRONMENTVARIABLES);
 launch_data_dict_insert(request,job,LAUNCH_KEY_SUBMITJOB);
 launch_data_t reply=launch_msg(request);
 int error=reply && launch_data_get_type(reply)==LAUNCH_DATA_ERRNO?launch_data_get_errno(reply):EPROTO;
 fprintf(stderr,"CORESIM_VOLUME_MANAGER_DIAGNOSTIC_SUBMIT error=%d\n",error);
 if(reply)launch_data_free(reply);launch_data_free(request);return error?1:0;
}
