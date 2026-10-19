#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

#ifdef LINUXCODE_OPTIONAL_PROVIDER
int linuxcode_optional_value(void) { return 83; }
#else
#ifdef LINUXCODE_REQUIRED_PROVIDER
extern int linuxcode_optional_value(void);
#else
extern int linuxcode_optional_value(void) __attribute__((weak_import));
#endif
int main(int argc,char **argv) {
    assert(argc == 2);
    int expected = atoi(argv[1]);
    puts("ABSENT_WEAK_MAIN_ENTERED");
    if (expected) {
        assert(linuxcode_optional_value && linuxcode_optional_value() == 83);
        assert(dlsym(RTLD_DEFAULT,"linuxcode_optional_value"));
        puts("WEAK_PROVIDER_PRESENT_REAL_FUNCTION_OK");
    } else {
        assert(!linuxcode_optional_value);
        assert(!dlsym(RTLD_DEFAULT,"linuxcode_optional_value"));
        puts("WEAK_PROVIDER_ABSENT_NULL_REFERENCE_OK");
    }
    return 0;
}
#endif
