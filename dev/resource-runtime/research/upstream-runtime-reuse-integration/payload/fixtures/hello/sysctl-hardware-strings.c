#include <sys/types.h>
#include <sys/sysctl.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int inspect(const char *name,int leaf) {
    size_t need=0; errno=0; int status=sysctlbyname(name,NULL,&need,NULL,0);
    printf("HW_STRING_SIZE name=%s status=%d errno=%d required=%zu\n",name,status,errno,need);
    if(status || need<2 || need>4096) return 1;
    unsigned char *data=malloc(need+16); if(!data)return 2; memset(data,0xa5,need+16);
    size_t used=need;errno=0;status=sysctlbyname(name,data,&used,NULL,0);
    int terminated=used>0&&used<=need&&data[used-1]==0;
    int guard=1;for(unsigned i=0;i<16;i++)if(data[need+i]!=0xa5)guard=0;
    printf("HW_STRING_COPY name=%s status=%d errno=%d size=%zu nul=%d guard=%d nonempty=%d\n",name,status,errno,used,terminated,guard,data[0]!=0);
    int exact=terminated&&strlen((const char*)data)+1==need;
    if(leaf==HW_MACHINE)exact=exact&&need==sizeof("x86_64")&&!memcmp(data,"x86_64",sizeof("x86_64"));
    printf("HW_STRING_EXACT name=%s complete=%d\n",name,exact);
    int failed=status||used!=need||!terminated||!guard||!data[0]||!exact;
    int mib[2]={CTL_HW,leaf};size_t numeric_need=0;errno=0;int numeric=sysctl(mib,2,NULL,&numeric_need,NULL,0);
    printf("HW_STRING_NUMERIC name=%s status=%d errno=%d required=%zu\n",name,numeric,errno,numeric_need);
    if(numeric || numeric_need!=need)failed=1;
    unsigned char *numeric_data=malloc(need);if(!numeric_data){free(data);return 2;}
    memset(numeric_data,0xa5,need);size_t numeric_used=need;errno=0;numeric=sysctl(mib,2,numeric_data,&numeric_used,NULL,0);
    int numeric_same=!numeric&&numeric_used==need&&!memcmp(data,numeric_data,need);
    printf("HW_STRING_NUMERIC_COPY name=%s status=%d errno=%d size=%zu identical=%d\n",name,numeric,errno,numeric_used,numeric_same);
    if(!numeric_same)failed=1;free(numeric_data);
    int resolved[16];size_t count=16;errno=0;int named=sysctlnametomib(name,resolved,&count);
    printf("HW_STRING_NAMETOMIB name=%s status=%d errno=%d count=%zu match=%d\n",name,named,errno,count,named==0&&count==2&&resolved[0]==CTL_HW&&resolved[1]==leaf);
    if(named||count!=2||resolved[0]!=CTL_HW||resolved[1]!=leaf)failed=1;
    unsigned char shortbuf[8];memset(shortbuf,0xa5,sizeof(shortbuf));size_t shortsize=1;errno=0;status=sysctlbyname(name,shortbuf,&shortsize,NULL,0);
    int untouched=1;for(unsigned i=0;i<sizeof(shortbuf);i++)if(shortbuf[i]!=0xa5)untouched=0;
    printf("HW_STRING_SHORT name=%s status=%d errno=%d size=%zu untouched=%d\n",name,status,errno,shortsize,untouched);
    /* XNU sysctl_old_user rejects before copying or advancing oldidx. */
    if(status!=-1||errno!=ENOMEM||shortsize!=0||!untouched)failed=1;
    unsigned char change=0;errno=0;status=sysctlbyname(name,NULL,NULL,&change,1);
    printf("HW_STRING_READONLY name=%s status=%d errno=%d\n",name,status,errno);
    if(status!=-1||(errno!=EPERM&&errno!=EACCES))failed=1;
    unsigned char *readonly_data=malloc(need);if(!readonly_data){free(data);return 2;}
    memset(readonly_data,0xa5,need);size_t readonly_size=need;errno=0;
    status=sysctlbyname(name,readonly_data,&readonly_size,&change,1);
    int no_old_write=1;for(size_t i=0;i<need;i++)if(readonly_data[i]!=0xa5)no_old_write=0;
    printf("HW_STRING_WRITE_READ name=%s status=%d errno=%d size=%zu untouched=%d\n",name,status,errno,readonly_size,no_old_write);
    if(status!=-1||errno!=EPERM||readonly_size!=need||!no_old_write)failed=1;
    readonly_size=1;errno=0;status=sysctlbyname(name,readonly_data,&readonly_size,&change,1);
    no_old_write=1;for(size_t i=0;i<need;i++)if(readonly_data[i]!=0xa5)no_old_write=0;
    printf("HW_STRING_WRITE_SHORT name=%s status=%d errno=%d size=%zu untouched=%d\n",name,status,errno,readonly_size,no_old_write);
    if(status!=-1||errno!=EPERM||readonly_size!=1||!no_old_write)failed=1;
    readonly_size=need;errno=0;status=sysctlbyname(name,readonly_data,&readonly_size,&change,0);
    int zero_new_read=!status&&readonly_size==need&&!memcmp(readonly_data,data,need);
    printf("HW_STRING_ZERO_NEW name=%s status=%d errno=%d size=%zu identical=%d\n",name,status,errno,readonly_size,zero_new_read);
    if(!zero_new_read)failed=1;free(readonly_data);
    free(data);return failed;
}
int main(void){setbuf(stdout,NULL);int machine=inspect("hw.machine",HW_MACHINE);int model=inspect("hw.model",HW_MODEL);printf("HW_STRINGS_RESULT machine=%d model=%d\n",machine,model);if(!machine&&!model)puts("HW_MODEL_AND_MACHINE_STRING_CONTRACT_NATIVE_OK");return machine||model;}
