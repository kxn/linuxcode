#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>

struct signatures { uint64_t file_start, blob_start, blob_size; };
static struct signatures valid(void) { return (struct signatures){16384,639920,23312}; }
static int rejected(int fd, void* input, int expected, const char* name) {
    errno=0;int rc=fcntl(fd,83,input);
    printf("%s rc=%d errno=%d expected=%d\n",name,rc,errno,expected);
    return rc==-1 && errno==expected;
}
int main(int argc,char** argv) {
    if (argc!=3) return 64;
    int fd=open(argv[1],O_RDONLY),bad=open(argv[2],O_RDONLY);
    if(fd<0 || bad<0)return 65;
    struct signatures input=valid();errno=0;
    int rc=fcntl(fd,83,&input);
    printf("genuine rc=%d errno=%d covered=%llu\n",rc,errno,(unsigned long long)input.file_start);
    if(rc || input.file_start!=639920 || input.blob_start!=639920 || input.blob_size!=23312)return 1;
    if(!rejected(fd,NULL,EFAULT,"null-pointer"))return 2;
    if(!rejected(fd,(void*)1,EFAULT,"invalid-pointer"))return 3;
    input=valid();input.blob_start++;
    if(!rejected(fd,&input,EINVAL,"wrong-range"))return 4;
    input=valid();if(!rejected(bad,&input,EPERM,"modified-code"))return 5;
    input=valid();if(!rejected(-1,&input,EBADF,"invalid-fd"))return 6;
    void* page=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    if(page==MAP_FAILED)return 7;
    *(struct signatures*)page=valid();if(mprotect(page,4096,PROT_READ))return 8;
    if(!rejected(fd,page,EFAULT,"readonly-result"))return 9;
    munmap(page,4096);close(bad);close(fd);
    puts("REAL_APPLE_SIMULATOR_DYLD_SIGNATURE_REGISTRATION_NATIVE_OK");return 0;
}
