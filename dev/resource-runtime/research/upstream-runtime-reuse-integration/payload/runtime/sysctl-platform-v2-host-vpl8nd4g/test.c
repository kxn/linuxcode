#include <darling/emulation/xnu_syscall/bsd/impl/misc/sysctl.h>
#include <darling/emulation/linux_premigration/ext/sys/utsname.h>
#include <sys/errno.h>
#include <stddef.h>
#include <stdint.h>
#include <mach/host_info.h>
extern int printf(const char*,...);
extern void* memcpy(void*,const void*,size_t);
extern void* memset(void*,int,size_t);
extern int memcmp(const void*,const void*,size_t);
extern size_t strlen(const char*);
extern int strcmp(const char*,const char*);
extern long host_linux_call(long,long,long,long,long,long,int);
static int mode, interrupted, opens, closes, reads;
static const char payload[]="Real Host Board\r\n";
long linux_syscall(long a,long b,long c,long d,long e,long f,int nr) {
 if(nr==257) {
  ++opens;
  if(strcmp((const char*)b,"/sys/class/dmi/id/product_name")||a!=-100||c!=0x80000)return -22;
  return mode==1 ? -2 : 777;
 }
 if(nr==0 && a==777) {
  ++reads;
  if(mode==2)return 0;
  if(mode==3 && !interrupted++){return -4;}
  if(mode==4){memset((void*)b,'X',c);return c;}
  if(mode==5)return -5;
  memcpy((void*)b,payload,sizeof(payload)-1);return sizeof(payload)-1;
 }
 if(nr==3 && a==777){++closes;return 0;}
 return host_linux_call(a,b,c,d,e,f,nr);
}
static struct linux_utsname info={.machine="host-test-arch"};
struct linux_utsname* need_uname(void){return &info;}
int read_string(const char*path,char*out,int size){return 0;}
long __simple_atoi(const char*s,char**end){return 0;}
int mach_port_deallocate(unsigned a,unsigned b){return 0;}
int host_info(unsigned a,int b,void*c,unsigned*d){return 0;}
unsigned mach_host_self(void){return 0;}
unsigned mach_task_self_=0;
const struct known_sysctl sysctls_kern[]={{.oid=-1}};
const struct known_sysctl sysctls_machdep[]={{.oid=-1}};
const struct known_sysctl sysctls_sysctl[]={{.oid=-1}};
const struct known_sysctl sysctls_net[]={{.oid=-1}};
const struct known_sysctl sysctls_vm[]={{.oid=-1}};
int strlcpy(char*out,const char*in,size_t n){size_t z=strlen(in);if(n){size_t c=z<n-1?z:n-1;memcpy(out,in,c);out[c]=0;}return z;}
static unsigned checks;
#define CHECK(x) do {checks++;if(!(x)){printf("FAIL line=%d check=%u\n",__LINE__,checks);return 1;}}while(0)
int main(void) {
 char buffer[512];unsigned long n;long status;const char*model="hw.model";
 for(mode=0;mode<6;mode++) {
  opens=closes=reads=interrupted=0;n=0;status=sys_sysctlbyname(model,8,0,&n,0,0);
  const char*expected=(mode==0||mode==3)?"Real Host Board":"Darling Virtual Platform";
  CHECK(status==0);CHECK(n==strlen(expected)+1);CHECK(opens==1);CHECK(closes==(mode==1?0:1));
  memset(buffer,0xa5,sizeof(buffer));unsigned long cap=n;
  status=sys_sysctlbyname(model,8,buffer,&cap,0,0);
  CHECK(status==0);CHECK(cap==n);CHECK(!strcmp(buffer,expected));CHECK((unsigned char)buffer[n]==0xa5);
  for(unsigned long size=0;size<n;size++) {
   memset(buffer,0xa5,sizeof(buffer));cap=size;
   status=sys_sysctlbyname(model,8,buffer,&cap,0,0);
   CHECK(status==-ENOMEM);CHECK(cap==0);CHECK((unsigned char)buffer[0]==0xa5);
  }
  int mib[]={CTL_HW,HW_MODEL};cap=sizeof(buffer);status=sys_sysctl(mib,2,buffer,&cap,0,0);
  CHECK(status==0);CHECK(!strcmp(buffer,expected));
 }
 mode=0;n=sizeof(buffer);status=sys_sysctlbyname("hw.machine",10,buffer,&n,0,0);
 CHECK(status==0);CHECK(n==strlen(info.machine)+1);CHECK(!strcmp(buffer,info.machine));
 const char *names[]={"hw.model","hw.machine"};
 for(int i=0;i<2;i++) {
  status=sys_sysctlbyname(names[i],strlen(names[i]),0,0,"forbidden",10);CHECK(status==-EPERM);
  n=sizeof(buffer);memset(buffer,0xa5,sizeof(buffer));status=sys_sysctlbyname(names[i],strlen(names[i]),buffer,&n,"forbidden",10);CHECK(status==-EPERM);CHECK(n==sizeof(buffer));for(unsigned at=0;at<sizeof(buffer);at++)CHECK((unsigned char)buffer[at]==0xa5);
  n=1;buffer[0]='!';status=sys_sysctlbyname(names[i],strlen(names[i]),buffer,&n,"forbidden",10);CHECK(status==-EPERM);CHECK(n==1);CHECK(buffer[0]=='!');
 }
 for(int i=0;i<2;i++) {
  n=sizeof(buffer);status=sys_sysctlbyname(names[i],strlen(names[i]),buffer,&n,"ignored",0);CHECK(status==0);CHECK(n>1);CHECK(buffer[n-1]==0);
  n=1;buffer[0]='!';status=sys_sysctlbyname(names[i],strlen(names[i]),buffer,&n,"ignored",0);CHECK(status==-ENOMEM);CHECK(n==0);CHECK(buffer[0]=='!');
  int mib[]={CTL_HW,i==0?HW_MODEL:HW_MACHINE};n=1;buffer[0]='!';status=sys_sysctl(mib,2,buffer,&n,"forbidden",10);CHECK(status==-EPERM);CHECK(n==1);CHECK(buffer[0]=='!');
  n=sizeof(buffer);status=sys_sysctl(mib,2,buffer,&n,"ignored",0);CHECK(status==0);CHECK(n>1);CHECK(buffer[n-1]==0);
 }
 int lookup[]={0,3},oid[2]={0};n=sizeof(oid);status=sys_sysctl(lookup,2,oid,&n,(void*)model,strlen(model));CHECK(status==0);CHECK(n==8);CHECK(oid[0]==CTL_HW&&oid[1]==HW_MODEL);
 int reverse[]={0,1,CTL_HW,HW_MODEL};n=sizeof(buffer);status=sys_sysctl(reverse,4,buffer,&n,0,0);CHECK(status==0);CHECK(!strcmp(buffer,model));CHECK(n==strlen(model)+1);
 n=sizeof(buffer);status=sys_sysctlbyname("hw.nonexistent",14,buffer,&n,0,0);CHECK(status==-ENOENT);
 CHECK(copyout_string("",buffer,&n)==0);CHECK(n==1);CHECK(buffer[0]==0);
 n=2;status=copyout_string("abc",0,&n);CHECK(status==0);CHECK(n==4);
 CHECK(copyout_string("abc",0,0)==0);CHECK(copyout_string("abc",buffer,0)==-EFAULT);
 printf("SYSCTL_PLATFORM_HOST_PASS checks=%u modes=6 native_execution=0\n",checks);return 0;
}
