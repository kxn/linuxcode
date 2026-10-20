#include <sys/stat.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <pthread.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"VCHROOT_LINKS_FAIL line=%d %s errno=%d\n",__LINE__,#x,errno);abort();}}while(0)
static int directoryFD;
static void repeated(char* output,unsigned count,const char* tail){output[0]=0;for(unsigned i=0;i<count;i++)strcat(output,"s/");strcat(output,tail);}
static void* small(void* value){CHECK(pthread_get_stacksize_np(pthread_self())==64*1024);struct stat st;CHECK(fstatat(directoryFD,"chain-0",&st,0)==0&&S_ISREG(st.st_mode));return NULL;}
int main(int argc,char** argv){setbuf(stdout,NULL);char directory[]="/tmp/vchroot-links.XXXXXX";CHECK(mkdtemp(directory));directoryFD=open(directory,O_RDONLY|O_DIRECTORY);CHECK(directoryFD>=0);CHECK(symlinkat(".",directoryFD,"s")==0);int fd=openat(directoryFD,"file",O_CREAT|O_WRONLY,0600);CHECK(fd>=0);CHECK(write(fd,"data",4)==4);close(fd);char path[512];struct stat st;
 if(argc>1&&!strcmp(argv[1],"baseline")){repeated(path,33,"file");errno=0;int result=fstatat(directoryFD,path,&st,0);printf("BASELINE_LINKS_33 result=%d errno=%d\n",result,errno);close(directoryFD);return result==0?2:0;}
 for(unsigned n=0;n<=32;n++){repeated(path,n,"file");CHECK(fstatat(directoryFD,path,&st,0)==0&&S_ISREG(st.st_mode));}
 for(unsigned n=33;n<=64;n++){repeated(path,n,"file");errno=0;CHECK(fstatat(directoryFD,path,&st,0)==-1&&errno==ELOOP);}
 repeated(path,32,"s");CHECK(fstatat(directoryFD,path,&st,AT_SYMLINK_NOFOLLOW)==0&&S_ISLNK(st.st_mode));
 for(unsigned n=0;n<32;n++){char name[32],target[32];snprintf(name,sizeof name,"chain-%u",n);if(n==31)strcpy(target,"file");else snprintf(target,sizeof target,"chain-%u",n+1);CHECK(symlinkat(target,directoryFD,name)==0);}
 CHECK(fstatat(directoryFD,"chain-0",&st,0)==0&&S_ISREG(st.st_mode));
 CHECK(symlinkat("chain-0",directoryFD,"chain-extra")==0);errno=0;CHECK(fstatat(directoryFD,"chain-extra",&st,0)==-1&&errno==ELOOP);
 pthread_attr_t attr;CHECK(!pthread_attr_init(&attr));CHECK(!pthread_attr_setstacksize(&attr,64*1024));pthread_t thread;CHECK(!pthread_create(&thread,&attr,small,NULL));CHECK(!pthread_attr_destroy(&attr));CHECK(!pthread_join(thread,NULL));
 char longTarget[1024];longTarget[0]=0;for(unsigned i=0;i<450;i++)strcat(longTarget,"./");strcat(longTarget,"file");CHECK(symlinkat(longTarget,directoryFD,"long-target")==0);CHECK(fstatat(directoryFD,"long-target",&st,0)==0&&S_ISREG(st.st_mode));
 char* longest=malloc(8192);CHECK(longest);for(unsigned i=0;i<511;i++){longest[2*i]='.';longest[2*i+1]='/';}longest[1022]='s';longest[1023]=0;CHECK(fstatat(directoryFD,longest,&st,0)==0&&S_ISDIR(st.st_mode));
 for(unsigned n=1024;n<=8192-1;n+=1023){memset(longest,'x',n);longest[n]=0;errno=0;CHECK(fstatat(directoryFD,longest,&st,0)==-1&&errno==ENAMETOOLONG);errno=0;CHECK(openat(directoryFD,longest,O_RDONLY)==-1&&errno==ENAMETOOLONG);}
 size_t page=getpagesize();char* guarded=mmap(NULL,2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);CHECK(guarded!=MAP_FAILED);CHECK(mprotect(guarded+page,page,PROT_NONE)==0);memcpy(guarded+page-5,"file",5);CHECK(fstatat(directoryFD,guarded+page-5,&st,0)==0&&S_ISREG(st.st_mode));errno=0;CHECK(fstatat(directoryFD,guarded+page,&st,0)==-1&&errno==EFAULT);errno=0;CHECK(openat(directoryFD,guarded+page,O_RDONLY)==-1&&errno==EFAULT);CHECK(munmap(guarded,2*page)==0);free(longest);
 for(unsigned n=0;n<32;n++){char name[32];snprintf(name,sizeof name,"chain-%u",n);CHECK(unlinkat(directoryFD,name,0)==0);}CHECK(unlinkat(directoryFD,"chain-extra",0)==0);CHECK(unlinkat(directoryFD,"long-target",0)==0);CHECK(unlinkat(directoryFD,"s",0)==0);CHECK(unlinkat(directoryFD,"file",0)==0);close(directoryFD);CHECK(rmdir(directory)==0);
 printf("VCHROOT_LINKS_LIMIT_BOUNDS_GUARD_AND_64K_STACK_OK checks=%u\n",checks);return 0;}
