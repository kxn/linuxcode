#include <darlingserver/linux-debug-registers.hpp>
#include <atomic>
#include <cassert>
#include <chrono>
#include <csignal>
#include <cstring>
#include <iostream>
#include <pthread.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <thread>
struct Shared { std::atomic<int> tid{0},usr{0},rt{0}; };
static Shared* shared;
static void signalHandler(int s) { if(s==SIGUSR1) ++shared->usr;else ++shared->rt; }
static void* worker(void*) { shared->tid=syscall(SYS_gettid);for(;;) pause(); }
struct Child {
 pid_t pid;
 Child() { pid=fork();assert(pid>=0);if(!pid){struct sigaction action={};action.sa_handler=signalHandler;sigemptyset(&action.sa_mask);assert(sigaction(SIGUSR1,&action,nullptr)==0);assert(sigaction(SIGRTMIN,&action,nullptr)==0);pthread_t t;assert(pthread_create(&t,nullptr,worker,nullptr)==0);for(;;)pause();} }
 ~Child() { kill(pid,SIGKILL);int status;while(waitpid(pid,&status,0)<0 && errno==EINTR){} }
};
static char state(pid_t pid) { char p[96],data[4096];snprintf(p,sizeof p,"/proc/%d/status",pid);int fd=open(p,O_RDONLY);if(fd<0)return '?';auto n=read(fd,data,sizeof data-1);close(fd);if(n<0)return '?';data[n]=0;auto s=strstr(data,"\nState:");return s?s[8]:'?'; }
#ifdef TEST_MACH_ABI
extern "C" int test_mach_debug_state(void*,int,int,void*,unsigned*,int);
extern "C" int test_mach_debug_constant(int);
struct DebugContext { pid_t tgid,tid;unsigned calls=0; };
extern "C" int linux_debug_state_host_access(void* opaque,uint64_t regs[8],bool write) {
 auto context=static_cast<DebugContext*>(opaque);++context->calls;
 int error=DarlingServer::accessLinuxDebugRegisters(context->tgid,context->tid,regs,write);
 if(!error)return 0;
 if(error==EPERM||error==EACCES)return test_mach_debug_constant(11);
 if(error==ESRCH)return test_mach_debug_constant(12);
 return test_mach_debug_constant(14);
}
#endif
static unsigned checks;
#define CHECK(x) do {++checks;if(!(x)){std::cerr<<"FAILED "<<__LINE__<<" "<<#x<<" errno="<<errno<<"\n";return 1;}}while(0)
int main(){shared=(Shared*)mmap(nullptr,sizeof(Shared),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);assert(shared!=MAP_FAILED);new(shared)Shared;Child child;for(int i=0;i<1000&&!shared->tid;i++)usleep(1000);pid_t tid=shared->tid;CHECK(tid>0&&tid!=child.pid);uint64_t initial[8],got[8];CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,initial,false)==0);std::cout<<"ACTUAL_DR6="<<std::hex<<initial[6]<<" DR7="<<initial[7]<<std::dec<<"\n";
 uint64_t changed[8];memcpy(changed,initial,sizeof changed);changed[0]=0x12345000;changed[1]=0x23456000;changed[7]=0x401;CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,changed,true)==0);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);CHECK(got[0]==changed[0]);CHECK(got[1]==changed[1]);CHECK((got[7]&1)==1);CHECK(got[4]==0&&got[5]==0);

#ifdef TEST_MACH_ABI
 DebugContext context{child.pid,tid};alignas(8) unsigned abi[20];memset(abi,0xa5,sizeof abi);unsigned count=20;
 const int generic=test_mach_debug_constant(0),narrow=test_mach_debug_constant(1),wide=test_mach_debug_constant(2);
 const unsigned genericCount=test_mach_debug_constant(3),narrowCount=test_mach_debug_constant(4),wideCount=test_mach_debug_constant(5);
 const int invalidCode=test_mach_debug_constant(6);CHECK(test_mach_debug_state(&context,1,generic,abi,&count,0)==0);CHECK(count==genericCount);CHECK(abi[0]==unsigned(wide)&&abi[1]==wideCount);uint64_t abiRegs[8];memcpy(abiRegs,abi+2,sizeof abiRegs);CHECK(abiRegs[0]==changed[0]&&abiRegs[1]==changed[1]);CHECK(test_mach_debug_state(&context,1,generic,abi,&count,1)==0);
 unsigned calls=context.calls;count=genericCount-1;CHECK(test_mach_debug_state(&context,1,generic,abi,&count,0)==invalidCode);CHECK(context.calls==calls);count=genericCount+1;CHECK(test_mach_debug_state(&context,1,generic,abi,&count,1)==invalidCode);CHECK(context.calls==calls);count=genericCount;abi[0]=narrow;CHECK(test_mach_debug_state(&context,1,generic,abi,&count,1)==invalidCode);CHECK(context.calls==calls);abi[0]=wide;abi[1]=wideCount-1;CHECK(test_mach_debug_state(&context,1,generic,abi,&count,1)==invalidCode);CHECK(context.calls==calls);
 count=wideCount;CHECK(test_mach_debug_state(&context,1,wide,abi,&count,0)==0);CHECK(count==wideCount);memcpy(abiRegs,abi,sizeof abiRegs);CHECK(abiRegs[0]==changed[0]);count=20;CHECK(test_mach_debug_state(&context,1,narrow,abi,&count,0)==invalidCode);
 // The same real Linux snapshot exercises 32-bit Mach ABI marshalling; this
 // host control does not claim execution of a 32-bit Darwin client.
 count=20;CHECK(test_mach_debug_state(&context,0,generic,abi,&count,0)==0);CHECK(count==genericCount);CHECK(abi[0]==unsigned(narrow)&&abi[1]==narrowCount);CHECK(abi[2]==uint32_t(changed[0])&&abi[3]==uint32_t(changed[1]));CHECK(test_mach_debug_state(&context,0,generic,abi,&count,1)==0);count=narrowCount;CHECK(test_mach_debug_state(&context,0,narrow,abi,&count,0)==0);CHECK(count==narrowCount);CHECK(abi[0]==uint32_t(changed[0]));count=20;CHECK(test_mach_debug_state(&context,0,wide,abi,&count,0)==invalidCode);CHECK(test_mach_debug_state(&context,1,wide,nullptr,&count,0)==invalidCode);CHECK(test_mach_debug_state(&context,1,wide,abi,nullptr,0)==invalidCode);
#endif
 CHECK(kill(child.pid,SIGSTOP)==0);int status;CHECK(waitpid(child.pid,&status,WUNTRACED)==child.pid);CHECK(WIFSTOPPED(status));CHECK(state(tid)=='T');CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);CHECK(state(tid)=='T');CHECK(state(child.pid)=='T');CHECK(syscall(SYS_tgkill,child.pid,tid,SIGUSR1)==0);for(int i=0;i<3;i++)CHECK(syscall(SYS_tgkill,child.pid,tid,SIGRTMIN)==0);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);CHECK(state(tid)=='T');CHECK(kill(child.pid,SIGCONT)==0);for(int i=0;i<1000&&(shared->usr<1||shared->rt<3);i++)usleep(1000);CHECK(shared->usr==1);CHECK(shared->rt==3);
 for(int i=0;i<20;i++){CHECK(syscall(SYS_tgkill,child.pid,tid,SIGRTMIN)==0);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);}for(int i=0;i<1000&&shared->rt<23;i++)usleep(1000);CHECK(shared->rt==23);
 CHECK(ptrace(PTRACE_SEIZE,tid,nullptr,nullptr)==0);memset(got,0xa5,sizeof got);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==EPERM);CHECK(got[0]==0xa5a5a5a5a5a5a5a5ULL);
#ifdef TEST_MACH_ABI
 count=wideCount;memset(abi,0xa5,sizeof abi);CHECK(test_mach_debug_state(&context,1,wide,abi,&count,0)==test_mach_debug_constant(7));CHECK(abi[0]==0xa5a5a5a5);
#endif
CHECK(ptrace(PTRACE_INTERRUPT,tid,nullptr,nullptr)==0);CHECK(waitpid(tid,&status,__WALL)==tid);CHECK(WIFSTOPPED(status));CHECK(ptrace(PTRACE_DETACH,tid,nullptr,nullptr)==0);
 uint64_t invalid[8];memcpy(invalid,changed,sizeof invalid);invalid[4]=1;CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,invalid,true)==EINVAL);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);CHECK(got[0]==changed[0]&&got[7]==changed[7]);invalid[4]=0;invalid[0]=~0ULL;CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,invalid,true)!=0);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);CHECK(got[0]==changed[0]&&got[1]==changed[1]&&got[7]==changed[7]);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,initial,true)==0);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==0);CHECK(memcmp(initial,got,sizeof got)==0);
 CHECK(DarlingServer::accessLinuxDebugRegisters(getpid(),tid,got,false)==ESRCH);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,nullptr,false)==EINVAL);CHECK(kill(child.pid,SIGKILL)==0);CHECK(waitpid(child.pid,&status,0)==child.pid);CHECK(DarlingServer::accessLinuxDebugRegisters(child.pid,tid,got,false)==ESRCH);
#ifdef TEST_MACH_ABI
 count=wideCount;CHECK(test_mach_debug_state(&context,1,wide,abi,&count,0)==test_mach_debug_constant(8));
#endif
std::cout<<"REAL_LINUX_DEBUG_REGISTER_"<<checks<<"_CHECKS_OK\n";return 0;}
