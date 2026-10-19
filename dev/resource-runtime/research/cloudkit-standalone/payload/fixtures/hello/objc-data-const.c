#include <assert.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <objc/runtime.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static vm_prot_t protection(void *pointer) {
    mach_vm_address_t start = (mach_vm_address_t)pointer;
    mach_vm_size_t size = 0;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t words = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object = MACH_PORT_NULL;
    assert(mach_vm_region(mach_task_self(), &start, &size, VM_REGION_BASIC_INFO_64,
        (vm_region_info_t)&info, &words, &object) == KERN_SUCCESS);
    assert(start <= (mach_vm_address_t)pointer && (mach_vm_address_t)pointer < start + size);
    if (object) assert(mach_port_deallocate(mach_task_self(), object) == KERN_SUCCESS);
    return info.protection;
}

int main(int argc, char **argv) {
    assert(argc == 3);
    // Heap copies prevent accidental equality with the plugin's string literals.
    char *first = strdup("linuxcodeDataConstValue:");
    char *second = strdup("linuxcodeDataConstOther:");
    SEL expected[] = {sel_registerName(first), sel_registerName(second)};
    free(first); free(second);
    void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!handle) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 1; }
    SEL *(*refs)(void) = dlsym(handle, "linuxcode_data_const_refs");
    long (*dispatch)(long) = dlsym(handle, "linuxcode_data_const_dispatch");
    assert(refs && dispatch);
    SEL *actual = refs();
    assert(actual[0] == expected[0] && actual[1] == expected[1]);
    vm_prot_t wanted = !strcmp(argv[2], "readonly") ? VM_PROT_READ : VM_PROT_READ | VM_PROT_WRITE;
    assert(protection(actual) == wanted);
    for (long i = -19; i <= 19; ++i) assert(dispatch(i) == i * 7 + 3);
    assert(protection(actual) == wanted);
    puts("OBJC_DATA_CONST_SELECTOR_IDENTITY_DISPATCH_PROTECTION_OK");
    return 0;
}
