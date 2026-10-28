/*
 * Local passwd/group membership for Darling OpenDirectory.
 * Contracts: Apple's Libinfo membership.h / mbr_check_membership.3 and
 * Libinfo-391 membership.c mbr_check_service_membership (all_services first).
 * No identity conversion, cached result, process getgroups, or synthesized
 * UUID alone establishes membership. This is not a SID/AD directory backend.
 */
#include "local-membership-check.h"
#include "identifier-translation.h"
#include <errno.h>
#include <grp.h>
#include <limits.h>
#include <pwd.h>
#include <stdint.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>

struct local_user { uid_t uid; gid_t primary; char *name; };
static const unsigned char everyone[16] =
    {0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0,0,0,12};

static int check_type(int type, bool user) {
    if (type==ID_TYPE_UUID || type==(user?ID_TYPE_UID:ID_TYPE_GID) ||
        type==(user?ID_TYPE_USERNAME:ID_TYPE_GROUPNAME)) return 0;
    switch (type) {
        case ID_TYPE_SID: case ID_TYPE_GROUP_NFS: case ID_TYPE_USER_NFS:
        case ID_TYPE_GSS_EXPORT_NAME: case ID_TYPE_X509_DN: case ID_TYPE_KERBEROS:
            return ENOTSUP;
        default:return EINVAL;
    }
}
static int local_id(int type,const void *value,size_t size,bool user,id_t *id) {
    int status=check_type(type,user);if(status)return status;
    void *result=NULL;size_t length=0;int kind=0;
    status=od_identifier_resolve(type,value,size,user?ID_TYPE_UID:ID_TYPE_GID,
        &result,&length,&kind);
    if(status)return status;
    if(!result || length!=sizeof(*id) || kind!=(user?MBR_REC_TYPE_USER:MBR_REC_TYPE_GROUP)) {
        free(result);return EIO;
    }
    memcpy(id,result,sizeof(*id));free(result);return 0;
}
static int user_record(id_t uid,struct local_user *user) {
    size_t size=4096;char *buffer=NULL;int status;
    for(;;) {
        char *next=realloc(buffer,size);if(!next){free(buffer);return ENOMEM;}buffer=next;
        struct passwd record,*found=NULL;
        status=getpwuid_r(uid,&record,buffer,size,&found);
        if(status==ERANGE) {if(size>SIZE_MAX/2){free(buffer);return ENOMEM;}size*=2;continue;}
        if(!status && !found)status=ENOENT;
        if(!status) {
            if(!record.pw_name || !*record.pw_name)status=EIO;
            else {user->name=strdup(record.pw_name);if(!user->name)status=ENOMEM;
                else {user->uid=record.pw_uid;user->primary=record.pw_gid;}}
        }
        free(buffer);return status;
    }
}
static int group_record(const char *name,gid_t wanted,gid_t *actual) {
    size_t size=4096;char *buffer=NULL;int status;
    for(;;) {
        char *next=realloc(buffer,size);if(!next){free(buffer);return ENOMEM;}buffer=next;
        struct group record,*found=NULL;
        status=name?getgrnam_r(name,&record,buffer,size,&found):getgrgid_r(wanted,&record,buffer,size,&found);
        if(status==ERANGE){if(size>SIZE_MAX/2){free(buffer);return ENOMEM;}size*=2;continue;}
        if(!status && !found)status=ENOENT;
        if(!status)*actual=record.gr_gid;
        free(buffer);return status;
    }
}
static int user_from_input(int type,const void *value,size_t size,struct local_user *user) {
    id_t uid;int status=local_id(type,value,size,true,&uid);
    return status?status:user_record(uid,user);
}
static int member_of(const struct local_user *user,gid_t group,int *member) {
    // Primary membership is a real passwd relation; the caller has already
    // checked that this group record exists.
    if(user->primary==group){*member=1;return 0;}
#ifdef __APPLE__
    typedef int list_gid_t; // Darwin getgrouplist uses signed int wire entries.
#else
    typedef gid_t list_gid_t;
#endif
    int capacity=16;list_gid_t *groups=NULL;
    for(;;) {
        if((size_t)capacity>SIZE_MAX/sizeof(*groups)){free(groups);return ENOMEM;}
        list_gid_t *next=realloc(groups,(size_t)capacity*sizeof(*groups));
        if(!next){free(groups);return ENOMEM;}groups=next;
        int count=capacity;errno=0;
        int status=getgrouplist(user->name,(list_gid_t)user->primary,groups,&count);
        if(status>=0) {
            if(count<0 || count>capacity){free(groups);return EIO;}
            for(int i=0;i<count;i++)if((gid_t)groups[i]==group){*member=1;break;}
            free(groups);return 0;
        }
        int error=errno;
        if(error && error!=ERANGE){free(groups);return error;}
        // Darwin's complete local-file backend reports the number filled,
        // unlike glibc's required count. Grow even when count<=capacity.
        if(capacity>INT_MAX/2){free(groups);return ENOMEM;}
        capacity=count>capacity?count:capacity*2;
    }
}
int linuxcode_check_membership(int user_type,const void *user,size_t user_size,
    int group_type,const void *group,size_t group_size,bool refresh,int *is_member) {
    (void)refresh;
    if(!is_member)return EINVAL;
    *is_member=0;
    if(!user || !user_size || !group || !group_size)return EINVAL;
    int status=check_type(group_type,false);if(status)return status;
    struct local_user record={0};status=user_from_input(user_type,user,user_size,&record);
    if(status)return status;
    // The documented UUID special cases apply to a valid local user. Unknown
    // users do not gain membership by presenting a compatibility UUID.
    if(user_type==ID_TYPE_UUID && user_size==16 && group_type==ID_TYPE_UUID && group_size==16 &&
        !memcmp(user,group,16)) {*is_member=1;free(record.name);return 0;}
    if(group_type==ID_TYPE_UUID && group_size==16 && !memcmp(group,everyone,16)) {
        *is_member=1;free(record.name);return 0;
    }
    id_t gid;status=local_id(group_type,group,group_size,false,&gid);
    if(!status){gid_t actual;status=group_record(NULL,gid,&actual);if(!status)status=member_of(&record,actual,is_member);}
    // A nonexistent group is a successful non-membership result (Apple man).
    if(status==ENOENT)status=0;
    free(record.name);if(status)*is_member=0;return status;
}
int linuxcode_check_service_membership(int user_type,const void *user,size_t user_size,
    const char *service,int *is_member) {
    static const char prefix[]="com.apple.access_";
    if(!is_member)return EINVAL;
    *is_member=0;
    if(!service || strnlen(service,256)>255-(sizeof(prefix)-1) || !user || !user_size)return EINVAL;
    struct local_user record={0};int status=user_from_input(user_type,user,user_size,&record);
    if(status)return status;
    gid_t gid;status=group_record("com.apple.access_all_services",0,&gid);
    if(status==ENOENT) {
        char name[256];memcpy(name,prefix,sizeof(prefix)-1);strcpy(name+sizeof(prefix)-1,service);
        status=group_record(name,0,&gid);
    }
    if(!status)status=member_of(&record,gid,is_member);
    free(record.name);if(status)*is_member=0;return status;
}
