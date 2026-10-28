#include <CoreFoundation/CoreFoundation.h>
#include <mach/mach.h>
#include <mach/task_info.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern int csops(pid_t, unsigned int, void *, size_t);
extern int csops_audittoken(pid_t, unsigned int, void *, size_t, audit_token_t *);
typedef struct __SecTask *SecTaskRef;
extern SecTaskRef SecTaskCreateFromSelf(CFAllocatorRef);
extern SecTaskRef SecTaskCreateWithAuditToken(CFAllocatorRef, audit_token_t);
extern CFTypeRef SecTaskCopyValueForEntitlement(SecTaskRef, CFStringRef, CFErrorRef *);
enum { OP_STATUS=0, OP_CDHASH=5, OP_XML=7, OP_DER=16 };
static unsigned checks;
static pid_t query_pid;
static audit_token_t *query_token;
static int query(unsigned op,void *data,size_t size) {
    return query_token ? csops_audittoken(query_pid,op,data,size,query_token) : csops(query_pid,op,data,size);
}
#define CHECK(v) do { ++checks; if (!(v)) { fprintf(stderr,"CSOPS_FAIL line=%d errno=%d\n",__LINE__,errno); return 1; } } while (0)

static int blob(unsigned op, const char *path) {
    FILE *f=fopen(path,"rb"); CHECK(f);
    CHECK(!fseek(f,0,SEEK_END)); long length=ftell(f); CHECK(length>=8 && length<1024*1024); rewind(f);
    unsigned char *expected=malloc((size_t)length), *actual=malloc((size_t)length+16); CHECK(expected && actual);
    CHECK(fread(expected,1,(size_t)length,f)==(size_t)length); fclose(f);
    uint32_t header[2]={0xa5a5a5a5,0xa5a5a5a5}; errno=0;
    CHECK(query(op,header,sizeof(header))==-1 && errno==ERANGE);
    const unsigned char *h=(const unsigned char *)header;
    CHECK(header[0]==0 && (((unsigned)h[4]<<24)|((unsigned)h[5]<<16)|((unsigned)h[6]<<8)|h[7])==(unsigned)length);
    memset(actual,0xa5,(size_t)length+16); CHECK(query(op,actual,(size_t)length)==0);
    CHECK(!memcmp(actual,expected,(size_t)length));
    for (unsigned i=0;i<16;++i) CHECK(actual[length+i]==0xa5);
    free(expected); free(actual); return 0;
}

int main(int argc,char **argv) {
    setbuf(stdout,NULL); alarm(20);
    if (argc==3 && !strcmp(argv[1],"--serve-token")) {
        audit_token_t token; mach_msg_type_number_t n=sizeof(token)/sizeof(natural_t);
        CHECK(task_info(mach_task_self(),TASK_AUDIT_TOKEN,(task_info_t)&token,&n)==KERN_SUCCESS);
        FILE *out=fopen(argv[2],"wb"); CHECK(out); CHECK(fwrite(&token,1,sizeof(token),out)==sizeof(token)); CHECK(!fclose(out));
        for (;;) pause();
    }
    int peer=argc==6 && !strcmp(argv[1],"--peer");
    CHECK(argc==2 || argc==5 || peer);
    audit_token_t token;
    if (peer) {
        FILE *in=fopen(argv[2],"rb"); CHECK(in); CHECK(fread(&token,1,sizeof(token),in)==sizeof(token)); fclose(in);
        CHECK(token.val[5]!=(unsigned)getpid()); query_pid=(pid_t)token.val[5]; query_token=&token;
    }
    unsigned flags=0xa5a5a5a5; CHECK(query(OP_STATUS,&flags,sizeof(flags))==0);
    if (argc==2) {
        CHECK(!strcmp(argv[1],"--unsigned")); CHECK(flags==0);
        unsigned char h[8]; errno=0; CHECK(csops(0,OP_DER,h,sizeof(h))==-1 && errno==EINVAL);
        printf("CSOPS_UNSIGNED_METADATA_OK checks=%u\n",checks); return 0;
    }
    CHECK(peer || !strcmp(argv[1],"--signed")); CHECK((flags&3)==3);
    // Actual file metadata does not establish Apple platform or enforcement identity.
    CHECK(!(flags & (0x04000000U|0x1000U)));
    CHECK(!blob(OP_XML,argv[peer?3:2])); CHECK(!blob(OP_DER,argv[peer?4:3]));
    unsigned char hash[20],expected_hash[20]; FILE *f=fopen(argv[peer?5:4],"rb"); CHECK(f);
    CHECK(fread(expected_hash,1,sizeof(expected_hash),f)==sizeof(expected_hash)); fclose(f);
    CHECK(query(OP_CDHASH,hash,sizeof(hash))==0); CHECK(!memcmp(hash,expected_hash,sizeof(hash)));
    if (!peer) {
        mach_msg_type_number_t n=sizeof(token)/sizeof(natural_t);
        CHECK(task_info(mach_task_self(),TASK_AUDIT_TOKEN,(task_info_t)&token,&n)==KERN_SUCCESS);
        CHECK(n==sizeof(token)/sizeof(natural_t)); CHECK(token.val[5]==(unsigned)getpid());
    }
    unsigned through_token=0; CHECK(csops_audittoken((pid_t)token.val[5],OP_STATUS,&through_token,sizeof(through_token),&token)==0); CHECK(through_token==flags);
    ++token.val[7]; through_token=0xa5a5a5a5; errno=0;
    CHECK(csops_audittoken((pid_t)token.val[5],OP_STATUS,&through_token,sizeof(through_token),&token)==-1 && errno==ESRCH); CHECK(through_token==0xa5a5a5a5);
    --token.val[7];
    errno=0; CHECK(query(OP_STATUS,(void *)(uintptr_t)1,sizeof(flags))==-1 && errno==EFAULT);
    SecTaskRef task=peer?SecTaskCreateWithAuditToken(NULL,token):SecTaskCreateFromSelf(NULL); CHECK(task);
    CFErrorRef error=NULL; CFTypeRef value=SecTaskCopyValueForEntitlement(task,CFSTR("org.linuxcode.csops.true"),&error);
    CHECK(!error && value && CFGetTypeID(value)==CFBooleanGetTypeID() && CFBooleanGetValue(value)); CFRelease(value);
    value=SecTaskCopyValueForEntitlement(task,CFSTR("org.linuxcode.csops.false"),&error);
    CHECK(!error && value && CFGetTypeID(value)==CFBooleanGetTypeID() && !CFBooleanGetValue(value)); CFRelease(value);
    value=SecTaskCopyValueForEntitlement(task,CFSTR("org.linuxcode.csops.text"),&error);
    CHECK(!error && value && CFGetTypeID(value)==CFStringGetTypeID() && CFEqual(value,CFSTR("actual-file-metadata"))); CFRelease(value);
    value=SecTaskCopyValueForEntitlement(task,CFSTR("org.linuxcode.csops.absent"),&error); CHECK(!error && !value);
    CFRelease(task); printf("CSOPS_SIGNED_METADATA_AND_ORIGINAL_SECTASK_OK checks=%u peer=%d\n",checks,peer); return 0;
}
