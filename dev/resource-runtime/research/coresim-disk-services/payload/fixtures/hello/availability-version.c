#include <dlfcn.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/sysctl.h>
typedef struct {uint32_t platform,version;} V;
typedef struct {unsigned major,minor,patch;} OS;
_Static_assert(sizeof(V)==8,"version record ABI");
typedef bool (*Check)(uint32_t,const V*);
static unsigned cases,failed;
static Check check;
static void expect(const char*name,uint32_t count,const V*versions,bool expected){
 bool actual=check(count,versions);++cases;if(actual!=expected)++failed;
 printf("AVAILABILITY_CASE %s expected=%u actual=%u\n",name,expected,actual);
}
int main(int argc,char**argv){
 if(argc!=2)return 2;uint32_t plist_version=(uint32_t)strtoul(argv[1],NULL,0);
 char system_version[48]={0};size_t length=sizeof(system_version);OS independent={0};
 if(sysctlbyname("kern.osproductversion",system_version,&length,NULL,0) ||
    sscanf(system_version,"%u.%u.%u",&independent.major,&independent.minor,&independent.patch)<1)return 5;
 uint32_t expected=(independent.major<<16)|(independent.minor<<8)|independent.patch;
 check=(Check)dlsym(RTLD_DEFAULT,"_availability_version_check");
 int(*get_version)(OS*)=dlsym(RTLD_DEFAULT,"os_system_version_get_current_version");
 if(!check || !get_version)return 3;
 OS os={0};if(get_version(&os))return 4;
 uint32_t packed=(os.major<<16)|(os.minor<<8)|os.patch;
 printf("AVAILABILITY_RUNNING_OS %u.%u.%u packed=%u expected=%u\n",os.major,os.minor,os.patch,packed,expected);
 printf("AVAILABILITY_VERSION_SOURCES sysctl=%s plist_packed=%u consistent=%u\n",system_version,plist_version,plist_version==expected);
 if(packed!=expected)++failed;
 V older={1,0},equal={1,expected},newer={1,expected+1},future={1,UINT32_MAX},other={2,UINT32_MAX},unknown={UINT32_MAX,UINT32_MAX};
 expect("empty",0,NULL,true);expect("old_macos",1,&older,true);expect("current_macos",1,&equal,true);expect("future_patch",1,&newer,false);expect("future_major",1,&future,false);
 expect("foreign_platform_unconstrained",1,&other,true);expect("unknown_platform_unconstrained",1,&unknown,true);
 V mixed1[]={other,equal},mixed2[]={future,other},mixed3[]={other,unknown},mixed4[]={other,unknown,equal};
 expect("matching_second",2,mixed1,true);expect("matching_first_future",2,mixed2,false);expect("all_other_platforms",2,mixed3,true);expect("matching_third",3,mixed4,true);
 V duplicate1[]={future,older},duplicate2[]={older,future};
 expect("first_duplicate_future_decides",2,duplicate1,false);expect("first_duplicate_old_decides",2,duplicate2,true);
 expect("defensive_null_array",1,NULL,false);
 printf("AVAILABILITY_COUNTS cases=%u failed=%u\n",cases,failed);
 if(!failed)puts("AVAILABILITY_VERSION_NATIVE_OK");return failed?1:0;
}
