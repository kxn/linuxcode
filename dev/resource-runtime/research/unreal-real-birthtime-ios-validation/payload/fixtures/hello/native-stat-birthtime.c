#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
static void emit(const char *name,struct stat *st,int result){assert(result==0);printf("BIRTHTIME_CASE %s %lld %ld\n",name,(long long)st->st_birthtimespec.tv_sec,st->st_birthtimespec.tv_nsec);}
int main(int argc,char **argv){assert(argc==2);setbuf(stdout,NULL);alarm(20);assert(chdir(argv[1])==0);struct stat st;int fd=open("regular",O_RDONLY);assert(fd>=0);int dir=open(".",O_RDONLY);assert(dir>=0);
#define CASE(name,call) do {memset(&st,0xa5,sizeof(st));int result=(call);emit(name,&st,result);}while(0)
CASE("stat-regular",stat("regular",&st));CASE("fstat-regular",fstat(fd,&st));CASE("stat-directory",stat("directory",&st));CASE("lstat-link",lstat("link",&st));CASE("stat-link-follow",stat("link",&st));CASE("fstatat-regular",fstatat(dir,"regular",&st,0));close(fd);fd=open("unlinked",O_RDONLY);assert(fd>=0);assert(unlink("unlinked")==0);CASE("fstat-unlinked",fstat(fd,&st));close(fd);close(dir);puts("BIRTHTIME_EXECUTION_OK");return 0;}
