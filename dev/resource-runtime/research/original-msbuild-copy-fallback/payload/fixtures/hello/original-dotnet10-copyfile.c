#include <assert.h>
#include <copyfile.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char** argv) {
    assert(argc == 5);
    setvbuf(stdout, NULL, _IONBF, 0);
    void* pal = dlopen(argv[1], RTLD_LAZY|RTLD_LOCAL); assert(pal);
    int32_t (*copy)(intptr_t, intptr_t, int64_t) = dlsym(pal, "SystemNative_CopyFile");
    assert(copy);
    Dl_info owner; assert(dladdr((void*)copy, &owner));
    printf("ORIGINAL_COPYFILE_BACKEND %s\n", owner.dli_fname);
    for (int i = 2; i < argc; ++i) {
        int source = open(argv[i], O_RDONLY); assert(source >= 0);
        struct stat st; assert(fstat(source, &st) == 0);
        off_t offsets[] = {-1, 0, 4096, st.st_size};
        for (unsigned j = 0; j < sizeof(offsets)/sizeof(offsets[0]); ++j) {
            int whence[] = {SEEK_DATA, SEEK_HOLE};
            for (unsigned k = 0; k < 2; ++k) {
                errno = 0;
                off_t result = lseek(source, offsets[j], whence[k]);
                printf("SEEK file=%d offset=%lld kind=%s result=%lld errno=%d\n",
                    i-2, (long long)offsets[j], k ? "hole" : "data", (long long)result, errno);
            }
        }
        assert(lseek(source, 0, SEEK_SET) == 0);
        char destination[1024];
        assert(snprintf(destination, sizeof(destination), "%s.copy", argv[i]) < sizeof(destination));
        int target = open(destination, O_CREAT|O_EXCL|O_RDWR, 0600); assert(target >= 0);
        errno = 0; int result = copy(source, target, st.st_size);
        printf("ORIGINAL_COPYFILE file=%d result=%d errno=%d\n", i-2, result, errno);
        close(target); close(source);
        /* Preserve failures and continue through component controls. */
        assert(snprintf(destination, sizeof(destination), "%s.sparsecopy", argv[i]) < sizeof(destination));
        errno = 0;
        result = copyfile(argv[i], destination, NULL, COPYFILE_DATA|COPYFILE_DATA_SPARSE);
        printf("ORIGINAL_SPARSE_COPYFILE file=%d result=%d errno=%d\n", i-2, result, errno);
        /* Preserve failures and continue through component controls. */
    }
    int source=open(argv[2],O_RDONLY);assert(source>=0);
    copyfile_flags_t flags[]={COPYFILE_DATA,COPYFILE_STAT,COPYFILE_XATTR,COPYFILE_ACL,COPYFILE_ALL};
    const char *names[]={"DATA","STAT","XATTR","ACL","ALL"};
    for (unsigned i=0;i<sizeof(flags)/sizeof(flags[0]);i++) {
        char target[1024];snprintf(target,sizeof(target),"%s.flag-%s",argv[2],names[i]);int destination=open(target,O_CREAT|O_EXCL|O_RDWR,0600);assert(destination>=0);assert(lseek(source,0,SEEK_SET)==0);errno=0;int result=fcopyfile(source,destination,NULL,flags[i]);printf("FCOPYFILE_COMPONENT %s result=%d errno=%d\n",names[i],result,errno);close(destination);
    }
    close(source);
    puts("ORIGINAL_DOTNET_COPYFILE_EXECUTION_OK");
    return 0;
}
