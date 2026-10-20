#include <Security/AuthSession.h>
#include <bsm/audit.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static void provider(const char *name) {
    void *fn=dlsym(RTLD_DEFAULT,name); Dl_info owner;
    if (!fn || !dladdr(fn,&owner)) { printf("AUDIT_PROVIDER_MISSING %s\n",name); return; }
    printf("AUDIT_PROVIDER %s %s\n",name,owner.dli_fname);
}
int main(void) {
    provider("SessionGetInfo"); provider("getaudit_addr"); provider("audit_session_self");
    SecuritySessionId sid=0xa5a5a5a5;
    SessionAttributeBits attrs=0xa5a5a5a5;
    OSStatus status=SessionGetInfo(callerSecuritySession,&sid,&attrs);
    printf("SESSION_INFO %d %u %u\n",(int)status,(unsigned)sid,(unsigned)attrs);
    auditinfo_addr_t info; memset(&info,0xa5,sizeof(info)); errno=0;
    int result=getaudit_addr(&info,sizeof(info));
    printf("AUDIT_INFO %d %d size=%zu auid=%u asid=%u flags=%llu type=%u\n",result,errno,sizeof(info),(unsigned)info.ai_auid,(unsigned)info.ai_asid,(unsigned long long)info.ai_flags,(unsigned)info.ai_termid.at_type);
    printf("PROCESS_IDENTITY uid=%u euid=%u pid=%d sid=%d\n",getuid(),geteuid(),getpid(),getsid(0));
    if (status || result) return 11;
    if (sid!=(SecuritySessionId)info.ai_asid || attrs!=(SessionAttributeBits)info.ai_flags) return 15;
    if (!sid || sid==callerSecuritySession) { puts("SECURITY_AUDIT_SESSION_INVALID_ID"); return 13; }
    puts("SECURITY_AUDIT_SESSION_IDENTITY_OK"); return 0;
}
