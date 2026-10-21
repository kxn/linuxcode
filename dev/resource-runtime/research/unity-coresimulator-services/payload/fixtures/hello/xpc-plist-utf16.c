#include <xpc/xpc.h>
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef xpc_object_t (*Create)(const void*,size_t);
int main(int argc,char** argv) {
    assert(argc>1 && (argc-1)%3==0);
    Create create=(Create)dlsym(RTLD_DEFAULT,"xpc_create_from_plist");assert(create);
    for (int i=1;i<argc;i+=3) {
        FILE* f=fopen(argv[i+1],"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0);rewind(f);
        void* bytes=malloc((size_t)n);assert(bytes && fread(bytes,1,(size_t)n,f)==(size_t)n);fclose(f);
        xpc_object_t object=create(bytes,(size_t)n);free(bytes);
        if (!strcmp(argv[i],"null")) assert(!object);
        else {
            assert(object && xpc_get_type(object)==XPC_TYPE_STRING);
            const char* actual=xpc_string_get_string_ptr(object);
            assert(xpc_string_get_length(object)==strlen(argv[i+2]));
            assert(actual && !strcmp(actual,argv[i+2]));xpc_release(object);
        }
        printf("XPC_PLIST_UTF16_CASE_OK %d\n",(i-1)/3);fflush(stdout);
    }
    puts("XPC_PLIST_UTF16_ALL_OK");return 0;
}
