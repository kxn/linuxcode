#include <assert.h>
#include <dlfcn.h>
#include <objc/runtime.h>
#include <stdio.h>

int main(int argc, char **argv) {
    assert(argc >= 3);
    puts("NATIVE_IMAGE_CLASS_MAIN_ENTERED");
    void *image = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!image) {
        fprintf(stderr, "NATIVE_IMAGE_DLOPEN_FAILED %s\n", dlerror());
        return 1;
    }
    for (int i = 2; i < argc; i++) {
        Class cls = objc_getClass(argv[i]);
        assert(cls && !class_isMetaClass(cls));
        assert(class_getName(cls) && class_getInstanceSize(cls) >= sizeof(void *));
        assert(class_isMetaClass(object_getClass((id)cls)));
        printf("NATIVE_IMAGE_CLASS %s size=%zu\n", class_getName(cls), class_getInstanceSize(cls));
    }
    printf("NATIVE_IMAGE_CLASS_LOAD_OK classes=%d\n", argc-2);
    return 0;
}
