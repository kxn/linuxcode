#include <unistd.h>
#include <errno.h>
long host_linux_call(long a,long b,long c,long d,long e,long f,int n){long r=syscall(n,a,b,c,d,e,f);return r<0?-errno:r;}
