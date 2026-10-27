#include <assert.h>
#include <notify.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>
extern bool ne_session_app_vpn_configs_present(void);
extern bool ne_session_always_on_vpn_configs_present(void);
extern bool ne_session_on_demand_configs_present(void);
static const char *key="com.apple.neconfigurationchanged";
static void set_state(int token,uint64_t value,bool post)
{
    assert(notify_set_state(token,value)==NOTIFY_STATUS_OK);
    if(post)assert(notify_post(key)==NOTIFY_STATUS_OK);
}
static bool await_present(bool expected)
{
    /* notify_post can return before the daemon updates its shared check slot. */
    for(unsigned i=0;i<2000;i++){
        if(ne_session_app_vpn_configs_present()==expected)return true;
        usleep(1000);
    }
    fprintf(stderr,"NE_CONFIG_NOTIFICATION_NOT_OBSERVED expected=%d\n",expected);return false;
}
static bool await_all(bool app,bool always,bool demand)
{
    for(unsigned i=0;i<2000;i++){
        if(ne_session_app_vpn_configs_present()==app && ne_session_always_on_vpn_configs_present()==always && ne_session_on_demand_configs_present()==demand)return true;
        usleep(1000);
    }
    return false;
}
int main(int argc,char **argv)
{
    setbuf(stdout,NULL);int token;assert(notify_register_check(key,&token)==NOTIFY_STATUS_OK);
    if(argc>1){assert(await_all(true,true,true));set_state(token,0,true);assert(notify_cancel(token)==NOTIFY_STATUS_OK);return 0;}
    uint64_t old;assert(notify_get_state(token,&old)==NOTIFY_STATUS_OK);
    set_state(token,0,true);assert(!ne_session_app_vpn_configs_present());
    set_state(token,UINT64_C(1)<<62,true);assert(await_present(true));
    set_state(token,0,false);assert(ne_session_app_vpn_configs_present());
    assert(notify_post(key)==NOTIFY_STATUS_OK);assert(await_present(false));
    set_state(token,(UINT64_C(1)<<63)|(UINT64_C(1)<<61)|1,true);assert(await_all(false,true,true));
    set_state(token,UINT64_MAX,true);assert(await_all(true,true,true));
    pid_t child=fork();assert(child>=0);
    if(!child){execl(argv[0],argv[0],"child",NULL);_exit(99);}
    int status;assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    assert(await_present(false));
    set_state(token,old,true);assert(notify_cancel(token)==NOTIFY_STATUS_OK);
    puts("NE_SESSION_REAL_NOTIFY_CONFIG_BITS_CACHED_POST_AND_EXEC_CHILD_VERIFIED");return 0;
}
