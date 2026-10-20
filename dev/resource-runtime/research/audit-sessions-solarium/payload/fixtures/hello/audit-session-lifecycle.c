#include <Security/AuthSession.h>
#include <bsm/audit.h>
#include <mach/mach.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"AUDIT_LIFECYCLE_FAIL %u %s errno=%d\n",checks,#x,errno); exit(15); } } while(0)
static auditinfo_addr_t get(void) {
    auditinfo_addr_t a; memset(&a,0xa5,sizeof(a));
    CHECK(getaudit_addr(&a,sizeof(a))==0);
    CHECK(a.ai_asid!=0 && (uint32_t)a.ai_asid!=UINT32_MAX);
    SecuritySessionId s=0;SessionAttributeBits flags=0x1234;
    CHECK(SessionGetInfo(callerSecuritySession,&s,&flags)==0);
    CHECK(s==(SecuritySessionId)a.ai_asid && flags==(SessionAttributeBits)a.ai_flags);
    CHECK(a.ai_flags==0); // A headless instance must not claim GUI/TTY access.
    audit_token_t token;mach_msg_type_number_t count=TASK_AUDIT_TOKEN_COUNT;
    CHECK(task_info(mach_task_self(),TASK_AUDIT_TOKEN,(task_info_t)&token,&count)==KERN_SUCCESS);
    CHECK(count==TASK_AUDIT_TOKEN_COUNT);
    CHECK(token.val[0]==a.ai_auid && token.val[6]==(uint32_t)a.ai_asid);
    CHECK(token.val[5]==(uint32_t)getpid() && token.val[7]!=0);
    return a;
}
static void child(const char *self, auditinfo_addr_t inherited, int fd) {
    auditinfo_addr_t a=get();CHECK(a.ai_asid==inherited.ai_asid && a.ai_auid==inherited.ai_auid);
    CHECK(a.ai_mask.am_success==inherited.ai_mask.am_success);
    a.ai_mask.am_success=0x76543210;a.ai_mask.am_failure=0x98765432;
    CHECK(setaudit_addr(&a,sizeof(a))==0);auditinfo_addr_t b=get();
    CHECK(b.ai_mask.am_success==a.ai_mask.am_success && b.ai_mask.am_failure==a.ai_mask.am_failure);
    char sid[32],auid[32],out[32];snprintf(sid,sizeof(sid),"%u",(unsigned)b.ai_asid);snprintf(auid,sizeof(auid),"%u",b.ai_auid);snprintf(out,sizeof(out),"%d",fd);
    execl(self,self,"exec-child",sid,auid,out,(char*)NULL);CHECK(0);
}
int main(int argc,char **argv) {
    if(argc==5 && !strcmp(argv[1],"exec-child")) {
        auditinfo_addr_t a=get();CHECK((unsigned)a.ai_asid==strtoul(argv[2],0,10));CHECK(a.ai_auid==strtoul(argv[3],0,10));CHECK(a.ai_mask.am_success==0x76543210 && a.ai_mask.am_failure==0x98765432);
        uint32_t ids[8];
        for(unsigned i=0;i<8;++i) {
            CHECK(SessionCreate(0,0)==0);auditinfo_addr_t b=get();ids[i]=b.ai_asid;CHECK(b.ai_asid!=a.ai_asid);CHECK(b.ai_auid==AU_DEFAUDITID);
            for(unsigned j=0;j<i;++j)CHECK(ids[j]!=ids[i]);
        }
        int fd=atoi(argv[4]);CHECK(write(fd,ids,sizeof(ids))==sizeof(ids));CHECK(close(fd)==0);
        printf("AUDIT_SESSION_EXEC_CHILD_OK %u\n",checks);return 0;
    }
    CHECK(argc==1);auditinfo_addr_t initial=get();
    unsigned char tail[64];memset(tail,0xa5,sizeof(tail));
    CHECK(getaudit_addr((auditinfo_addr_t*)tail,4)==0);CHECK(!memcmp(tail,&initial,4));
    for(unsigned i=4;i<sizeof(tail);++i)CHECK(tail[i]==0xa5);
    CHECK(getaudit_addr(NULL,0)==0);
    errno=0;CHECK(getaudit_addr((auditinfo_addr_t*)(uintptr_t)1,sizeof(initial))==-1 && errno==EFAULT);
    errno=0;CHECK(setaudit_addr((auditinfo_addr_t*)(uintptr_t)1,sizeof(initial))==-1 && errno==EFAULT);
    errno=0;CHECK(setaudit_addr(NULL,0)==-1 && errno==EINVAL);
    auditinfo_addr_t invalid=initial;invalid.ai_termid.at_type=99;
    errno=0;CHECK(setaudit_addr(&invalid,sizeof(invalid))==-1 && errno==EINVAL);
    invalid=initial;invalid.ai_flags=0x10;invalid.ai_asid=AU_ASSIGN_ASID;
    errno=0;CHECK(setaudit_addr(&invalid,sizeof(invalid))==-1 && errno==EINVAL);
    CHECK(get().ai_asid==initial.ai_asid);
    initial.ai_mask.am_success=0x12345678;initial.ai_mask.am_failure=0x23456789;
    CHECK(setaudit_addr(&initial,sizeof(initial))==0);
    uint32_t all[16];
    for(unsigned c=0;c<2;++c) {
        int fds[2];CHECK(pipe(fds)==0);pid_t p=fork();CHECK(p>=0);
        if(!p){close(fds[0]);child(argv[0],initial,fds[1]);return 16;}
        CHECK(close(fds[1])==0);size_t have=0;
        while(have<sizeof(all)/2){ssize_t n=read(fds[0],(char*)(all+c*8)+have,sizeof(all)/2-have);CHECK(n>0);have+=n;}
        CHECK(close(fds[0])==0);int status;CHECK(waitpid(p,&status,0)==p);CHECK(WIFEXITED(status)&&WEXITSTATUS(status)==0);
        auditinfo_addr_t unchanged=get();CHECK(unchanged.ai_asid==initial.ai_asid && unchanged.ai_auid==initial.ai_auid);
        CHECK(unchanged.ai_mask.am_success==initial.ai_mask.am_success && unchanged.ai_mask.am_failure==initial.ai_mask.am_failure);
    }
    for(unsigned i=0;i<16;++i){CHECK(all[i]!=initial.ai_asid);for(unsigned j=0;j<i;++j)CHECK(all[i]!=all[j]);}
    printf("AUDIT_SESSION_FORK_EXEC_CREATE_MASK_ISOLATION_MACH_TOKEN_AND_ERRORS_OK %u\n",checks);return 0;
}
