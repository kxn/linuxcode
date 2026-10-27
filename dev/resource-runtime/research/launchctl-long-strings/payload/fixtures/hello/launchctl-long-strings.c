#include <CoreFoundation/CoreFoundation.h>
#include "launch.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main launchctl_original_main
#include "../../vendor/darling/src/launchd/support/launchctl.c"
#undef main
static unsigned checks;
#define CHECK(x) do{if(!(x)){fprintf(stderr,"LAUNCHCTL_CHECK_FAILED %d\n",__LINE__);return 1;}checks++;}while(0)
int main(void){
    setbuf(stdout,NULL);
    const size_t lengths[]={0,1,4094,4095,4096,4142,16384,100000};
    for(unsigned i=0;i<sizeof lengths/sizeof lengths[0];i++){
        size_t n=lengths[i];char *bytes=malloc(n+1);memset(bytes,'L',n);bytes[n]=0;
        CFStringRef s=CFStringCreateWithCString(NULL,bytes,kCFStringEncodingUTF8);CHECK(s);
        launch_data_t d=CF2launch_data(s);CHECK(d&&launch_data_get_type(d)==LAUNCH_DATA_STRING);
        CHECK(strlen(launch_data_get_string(d))==n);CHECK(!memcmp(launch_data_get_string(d),bytes,n+1));
        launch_data_free(d);CFRelease(s);free(bytes);
    }
    CFMutableStringRef utf=CFStringCreateMutable(NULL,0);
    for(unsigned i=0;i<8192;i++)CFStringAppend(utf,CFSTR("签名路径/"));
    CFIndex maximum=CFStringGetMaximumSizeForEncoding(CFStringGetLength(utf),kCFStringEncodingUTF8)+1;
    char *expected=malloc(maximum);CHECK(CFStringGetCString(utf,expected,maximum,kCFStringEncodingUTF8));
    const void *keys[]={CFSTR("EnvironmentVariables"),CFSTR("ProgramArguments")};
    const void *ek[]={CFSTR("DYLD_LIBRARY_PATH")},*ev[]={utf};
    CFDictionaryRef environment=CFDictionaryCreate(NULL,ek,ev,1,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    const void *av[]={CFSTR("/usr/bin/env"),utf};CFArrayRef arguments=CFArrayCreate(NULL,av,2,&kCFTypeArrayCallBacks);
    const void *values[]={environment,arguments};CFDictionaryRef job=CFDictionaryCreate(NULL,keys,values,2,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    launch_data_t result=CF2launch_data(job);CHECK(result);
    launch_data_t env=launch_data_dict_lookup(result,"EnvironmentVariables");CHECK(env);
    CHECK(!strcmp(launch_data_get_string(launch_data_dict_lookup(env,"DYLD_LIBRARY_PATH")),expected));
    launch_data_t args=launch_data_dict_lookup(result,"ProgramArguments");CHECK(args);
    CHECK(!strcmp(launch_data_get_string(launch_data_array_get_index(args,1)),expected));
    launch_data_free(result);CFRelease(job);CFRelease(arguments);CFRelease(environment);CFRelease(utf);free(expected);
    const UniChar nul[]={65,0,66};CFStringRef embedded=CFStringCreateWithCharacters(NULL,nul,3);
    CHECK(CF2launch_data(embedded)==NULL);CFRelease(embedded);
    printf("LAUNCHCTL_LONG_STRINGS_OK %u\n",checks);return 0;
}
