/* Owned records-only host fixture; can also be compiled as a Darwin probe.
 * The --private-records mode is run only inside an isolated Linux chroot. */
#include "local-membership-check.h"
#include "identifier-translation.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pwd.h>
#include <grp.h>
#include <unistd.h>
#include <stdint.h>
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"LOCAL_MEMBERSHIP_FAIL line=%d errno=%d\n",__LINE__,errno);return 1;}}while(0)
static int uuid_for(id_t id,unsigned char uuid[16]) {
 void *p=NULL;size_t n=0;int kind=0;int e=od_identifier_resolve(ID_TYPE_UID,&id,4,ID_TYPE_UUID,&p,&n,&kind);
 if(e)return e;if(n!=16){free(p);return EIO;}memcpy(uuid,p,16);free(p);return 0;
}
static int check(unsigned char user[16],gid_t gid,int expected) {
 int member=-1;int e=linuxcode_check_membership(ID_TYPE_UUID,user,16,ID_TYPE_GID,&gid,4,false,&member);
 return e || member!=expected;
}
static int live(void) {
 struct passwd *pw=getpwuid(getuid());CHECK(pw);id_t uid=pw->pw_uid;gid_t primary=pw->pw_gid;unsigned char uuid[16];CHECK(!uuid_for(uid,uuid));CHECK(!check(uuid,primary,1));
 struct group *g;setgrent();gid_t supplementary=0;int found=0;
 while((g=getgrent())){if(g->gr_gid==primary)continue;for(char **p=g->gr_mem;p&&*p;p++)if(!strcmp(*p,pw->pw_name)){supplementary=g->gr_gid;found=1;break;}if(found)break;}endgrent();
 if(found)CHECK(!check(uuid,supplementary,1));
 printf("LOCAL_MEMBERSHIP_REAL_NSS_OK checks=%u supplementary=%d\n",checks,found);return 0;
}
#ifndef __APPLE__
static void add_group(const char *name,unsigned gid,const char *member) {
 FILE*f=fopen("/etc/group","a");if(!f)abort();fprintf(f,"%s:x:%u:%s\n",name,gid,member);if(fclose(f))abort();
}
#endif
int main(int argc,char **argv) {
 setbuf(stdout,NULL);if(argc==1)return live();
#ifdef __APPLE__
 (void)argv;CHECK(argc==1);return 1;
#else
 CHECK(argc==2&&!strcmp(argv[1],"--private-records"));
 CHECK(geteuid()==0 && !access("/.local-membership-fixture-root",R_OK));
 unsigned char alice[16],bob[16],missing[16],everyone[16]={0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0,0,0,12};CHECK(!uuid_for(1001,alice));CHECK(!uuid_for(1002,bob));CHECK(!uuid_for(9999999,missing));
 CHECK(!check(alice,1000,1));CHECK(!check(alice,2000,1));CHECK(!check(bob,2000,0));CHECK(!check(alice,3039,1));CHECK(!check(alice,2001,0));CHECK(!check(alice,9999999,0));
 int m=7;gid_t gid=2000;CHECK(linuxcode_check_membership(ID_TYPE_UUID,missing,16,ID_TYPE_GID,&gid,4,false,&m)==ENOENT&&m==0);
 m=7;CHECK(!linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_UUID,alice,16,false,&m)&&m==1);
 m=7;CHECK(!linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_UUID,everyone,16,false,&m)&&m==1);
 m=7;CHECK(linuxcode_check_membership(ID_TYPE_UUID,missing,16,ID_TYPE_UUID,everyone,16,false,&m)==ENOENT&&m==0);
 m=7;CHECK(linuxcode_check_membership(ID_TYPE_UUID,alice,15,ID_TYPE_GID,&gid,4,false,&m)==EINVAL&&m==0);
 m=7;CHECK(linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_GID,&gid,3,false,&m)==EINVAL&&m==0);
 m=7;CHECK(linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_SID,&gid,4,false,&m)==ENOTSUP&&m==0);
 m=7;CHECK(linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_GROUP_NFS,"x",1,false,&m)==ENOTSUP&&m==0);
 unsigned char opaque[16]={1,2,3};m=7;CHECK(linuxcode_check_membership(ID_TYPE_UUID,opaque,16,ID_TYPE_GID,&gid,4,false,&m)==ENOENT&&m==0);
 m=7;CHECK(!linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_UUID,opaque,16,false,&m)&&m==0);
 m=7;CHECK(linuxcode_check_membership(ID_TYPE_USERNAME,"alice\0x",7,ID_TYPE_GID,&gid,4,false,&m)==EINVAL&&m==0);
 CHECK(linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_GID,&gid,4,false,NULL)==EINVAL);
 m=7;CHECK(linuxcode_check_service_membership(ID_TYPE_UUID,alice,16,"ssh",&m)==ENOENT&&m==0);
 add_group("com.apple.access_ssh",5000,"alice");m=7;CHECK(!linuxcode_check_service_membership(ID_TYPE_UUID,alice,16,"ssh",&m)&&m==1);
 m=7;CHECK(!linuxcode_check_service_membership(ID_TYPE_UUID,bob,16,"ssh",&m)&&m==0);
 add_group("com.apple.access_all_services",5001,"bob");m=7;CHECK(!linuxcode_check_service_membership(ID_TYPE_UUID,alice,16,"ssh",&m)&&m==0);
 m=7;CHECK(!linuxcode_check_service_membership(ID_TYPE_UUID,bob,16,"ssh",&m)&&m==1);
 m=7;CHECK(!linuxcode_check_service_membership(ID_TYPE_UUID,bob,16,"undefined",&m)&&m==1);
 char overlong[256];memset(overlong,'a',255);overlong[255]=0;m=7;CHECK(linuxcode_check_service_membership(ID_TYPE_UUID,alice,16,overlong,&m)==EINVAL&&m==0);
 m=7;CHECK(linuxcode_check_service_membership(ID_TYPE_UUID,alice,16,NULL,&m)==EINVAL&&m==0);
 add_group("new-current-record",6000,"alice");gid=6000;m=7;CHECK(!linuxcode_check_membership(ID_TYPE_UUID,alice,16,ID_TYPE_GID,&gid,4,true,&m)&&m==1);
 printf("LOCAL_MEMBERSHIP_PRIVATE_NSS_RECORDS_OK checks=%u includes_over_16_supplementary_and_SACL_priority\n",checks);return 0;
#endif
}
