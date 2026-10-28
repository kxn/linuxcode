/* Original Libinfo -> actual OpenDirectory daemon; read-only local records. */
#include <membership.h>
#include <membershipPriv.h>
#include <pwd.h>
#include <grp.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"MEMBERSHIP_PROTOCOL_FAIL line=%d errno=%d\n",__LINE__,errno);return 1;}}while(0)
int main(void) {
 setbuf(stdout,NULL);alarm(20);
 struct passwd *pw=getpwuid(getuid());CHECK(pw);uid_t uid=pw->pw_uid;gid_t primary=pw->pw_gid;CHECK(getgrgid(primary));
 uuid_t user,group,unknown_user,unknown_group,everyone={0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0,0,0,12};
 CHECK(!mbr_uid_to_uuid(uid,user));CHECK(!mbr_gid_to_uuid(primary,group));int member=7;
 CHECK(!mbr_check_membership(user,group,&member)&&member==1);member=7;CHECK(!mbr_check_membership_by_id(user,primary,&member)&&member==1);
 member=7;CHECK(!mbr_check_membership(user,user,&member)&&member==1);member=7;CHECK(!mbr_check_membership(user,everyone,&member)&&member==1);
 uid_t absent=2147480000U;CHECK(!getpwuid(absent));CHECK(!getgrgid(absent));CHECK(!mbr_uid_to_uuid(absent,unknown_user));CHECK(!mbr_gid_to_uuid(absent,unknown_group));
 member=7;CHECK(!mbr_check_membership(user,unknown_group,&member)&&member==0);
 member=7;CHECK(mbr_check_membership(unknown_user,group,&member)==ENOENT&&member==0);
 uuid_t opaque={1,2,3};member=7;CHECK(mbr_check_membership(opaque,group,&member)==ENOENT&&member==0);
 if(!getgrnam("com.apple.access_all_services")) {
  CHECK(!getgrnam("com.apple.access_org.linuxcode.absent.protocol.fixture"));member=7;
  CHECK(mbr_check_service_membership(user,"org.linuxcode.absent.protocol.fixture",&member)==ENOENT&&member==0);
 }
 char long_service[256];memset(long_service,'a',255);long_service[255]=0;member=7;
 CHECK(mbr_check_service_membership(user,long_service,&member)==EINVAL&&member==0);
 CHECK(!mbr_reset_cache());member=7;CHECK(!mbr_check_membership_refresh(user,group,&member)&&member==1);
 printf("MEMBERSHIP_ORIGINAL_LIBINFO_DAEMON_PROTOCOL_OK checks=%u numeric_and_UUID_primary_unknown_group_unknown_user_SACL_refresh\n",checks);return 0;
}
