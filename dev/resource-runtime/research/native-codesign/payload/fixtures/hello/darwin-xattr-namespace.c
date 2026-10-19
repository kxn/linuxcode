#include <sys/xattr.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"XATTR_FAIL line %d errno %d: %s\n",__LINE__,errno,#x);return 1;}}while(0)
static int listed(const char *names,ssize_t size,const char *key) {int n=0;for(ssize_t i=0;i<size;i+=strlen(names+i)+1)if(!strcmp(names+i,key))n++;return n;}
int main(int argc,char **argv){
    setbuf(stdout,NULL);CHECK(argc==2);CHECK(chdir(argv[1])==0);int fd=open("item",O_RDWR|O_CREAT|O_EXCL,0600);CHECK(fd>=0);CHECK(write(fd,"payload",7)==7);
    const unsigned char bytes[]={0,128,255,65};unsigned char out[32];errno=0;
    CHECK(getxattr(".","com.apple.FinderInfo",out,sizeof out,0,0)==-1&&errno==ENOATTR);
    CHECK(setxattr("item","com.apple.cs.Test",bytes,sizeof bytes,0,XATTR_CREATE)==0);
    CHECK(getxattr("item","com.apple.cs.Test",NULL,0,0,0)==4);
    CHECK(fgetxattr(fd,"com.apple.cs.Test",out,sizeof out,0,0)==4&&memcmp(out,bytes,4)==0);
    errno=0;CHECK(getxattr("item","com.apple.cs.Test",out,3,0,0)==-1&&errno==ERANGE);
    errno=0;CHECK(setxattr("item","com.apple.cs.Test",bytes,4,0,XATTR_CREATE)==-1&&errno==EEXIST);
    errno=0;CHECK(fsetxattr(fd,"missing",bytes,4,0,XATTR_REPLACE)==-1&&errno==ENOATTR);
    CHECK(fsetxattr(fd,"com.apple.cs.Test","ok",2,0,XATTR_REPLACE)==0);
    CHECK(getxattr("item","com.apple.cs.Test",out,sizeof out,0,0)==2&&memcmp(out,"ok",2)==0);
    CHECK(setxattr("item","com.apple.cs.Test",bytes,4,0,XATTR_REPLACE)==0);
    CHECK(setxattr("item","linuxcode.alpha","first",5,0,0)==0);
    CHECK(setxattr("item","user.linuxcode.alpha","second",6,0,0)==0);
    CHECK(fgetxattr(fd,"linuxcode.alpha",out,sizeof out,0,0)==5&&memcmp(out,"first",5)==0);
    CHECK(getxattr("item","user.linuxcode.alpha",out,sizeof out,0,0)==6&&memcmp(out,"second",6)==0);
    CHECK(setxattr("item","com.apple.quarantine","0000;00000000;fixture;",22,0,0)==0);
    CHECK(setxattr("item","user.com.apple.quarantine","shadow",6,0,0)==0);
    char names[1024];ssize_t needed=listxattr("item",NULL,0,0);CHECK(needed>0&&needed<1024);CHECK(listxattr("item",names,needed,0)==needed);
    const char *expected[]={"com.apple.cs.Test","linuxcode.alpha","user.linuxcode.alpha","com.apple.quarantine","user.com.apple.quarantine"};
    for(unsigned i=0;i<5;i++)CHECK(listed(names,needed,expected[i])==1);
    errno=0;CHECK(flistxattr(fd,names,needed-1,0)==-1&&errno==ERANGE);CHECK(flistxattr(fd,names,needed,0)==needed);
    errno=0;CHECK(listxattr("item",(char*)1,needed,0)==-1&&errno==EFAULT);
    errno=0;CHECK(fgetxattr(fd,(char*)1,out,sizeof out,0,0)==-1&&errno==EFAULT);
    CHECK(symlink("item","link")==0);CHECK(getxattr("link","com.apple.cs.Test",out,sizeof out,0,0)==4&&memcmp(out,bytes,4)==0);
    CHECK(listxattr("link",names,sizeof names,XATTR_NOFOLLOW)==0);
    CHECK(fremovexattr(fd,"linuxcode.alpha",0)==0);errno=0;CHECK(getxattr("item","linuxcode.alpha",out,sizeof out,0,0)==-1&&errno==ENOATTR);
    CHECK(removexattr("item","user.linuxcode.alpha",0)==0);errno=0;CHECK(removexattr("item","user.linuxcode.alpha",0)==-1&&errno==ENOATTR);
    CHECK(close(fd)==0);printf("DARWIN_XATTR_REAL_NAMESPACE_PATH_FD_SIZE_ERRORS_SYMLINK_AND_QUARANTINE_ALIAS_OK %u\n",checks);return 0;
}
