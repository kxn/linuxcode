#include <xpc/xpc.h>
#include <dlfcn.h>
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef xpc_object_t (*Create)(const char *,bool);
typedef char *(*Description)(xpc_rich_error_t);
typedef bool (*Retry)(xpc_rich_error_t);
int main(int argc,char **argv) {
    assert(argc==2);
    void *library=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
    if (!library) { fprintf(stderr,"%s\n",dlerror());return 1; }
    Create create=(Create)dlsym(library,"darling_xpc_rich_error_create");
    Description description=(Description)dlsym(library,"xpc_rich_error_copy_description");
    Retry retry=(Retry)dlsym(library,"xpc_rich_error_can_retry");
    const void *type=dlsym(library,"_xpc_type_rich_error");
    xpc_object_t peer=dlsym(library,"_xpc_error_peer_code_signing_requirement");
    assert(create && description && retry && type && peer);
    Dl_info owner;assert(dladdr((void *)description,&owner));
    char *actual=realpath(owner.dli_fname,NULL),*expected=realpath(argv[1],NULL);
    assert(actual && expected && !strcmp(actual,expected));free(actual);free(expected);
    const char *cases[]={"","failure","temporary failure","中文：连接失败","line one\nline two"};
    for (unsigned i=0;i<5;i++) for (unsigned canRetry=0;canRetry<2;canRetry++) for (unsigned repeat=0;repeat<16;repeat++) {
        char input[128];strcpy(input,cases[i]);
        xpc_object_t object=create(input,canRetry);assert(object && xpc_get_type(object)==type);
        memset(input,'!',strlen(input));
        xpc_object_t copy=xpc_copy(object);assert(copy==object);xpc_release(object);
        xpc_retain(copy);xpc_release(copy);
        assert(retry((xpc_rich_error_t)copy)==(bool)canRetry);
        char *first=description((xpc_rich_error_t)copy),*second=description((xpc_rich_error_t)copy);
        assert(first && second && first!=second && !strcmp(first,cases[i]) && !strcmp(second,cases[i]));
        if (*first) *first='?';assert(!strcmp(second,cases[i]));free(first);free(second);
        char *publicDescription=xpc_copy_description(copy);
        assert(publicDescription && !strcmp(publicDescription,cases[i]));free(publicDescription);
        xpc_release(copy);
    }
    errno=0;assert(create(NULL,false)==NULL && errno==EINVAL);
    assert(xpc_get_type(peer)==XPC_TYPE_ERROR);
    assert(xpc_dictionary_get_count(peer)==1);
    assert(!strcmp(xpc_dictionary_get_string(peer,XPC_ERROR_KEY_DESCRIPTION),"Peer Forbidden"));
    for (unsigned i=0;i<32;i++) { assert(xpc_retain(peer)==peer);xpc_release(peer); }
    // Existing Darling OS_xpc_error inherits dictionary copying, which
    // produces a dictionary. Check its actual preserved contents and record
    // that existing type-preservation limitation instead of hiding it.
    xpc_object_t peerCopy=xpc_copy(peer);assert(peerCopy && xpc_get_type(peerCopy)==XPC_TYPE_DICTIONARY);
    assert(!strcmp(xpc_dictionary_get_string(peerCopy,XPC_ERROR_KEY_DESCRIPTION),"Peer Forbidden"));
    xpc_dictionary_set_string(peerCopy,XPC_ERROR_KEY_DESCRIPTION,"changed copy");
    assert(!strcmp(xpc_dictionary_get_string(peer,XPC_ERROR_KEY_DESCRIPTION),"Peer Forbidden"));
    xpc_release(peerCopy);
    char *peerText=xpc_copy_description(peer);
    assert(peerText && strstr(peerText,"Peer Forbidden"));free(peerText);
    puts("XPC_RICH_ERROR_ACTUAL_OBJECTS_COPY_RETRY_RETAIN_AND_PEER_ERROR_OK");
    return 0;
}
