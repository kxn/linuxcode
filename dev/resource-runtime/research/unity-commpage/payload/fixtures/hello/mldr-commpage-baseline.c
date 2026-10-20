/* Reproduce the original ignored-address-hint bug with real Linux mappings. */
#include COMMPAGE_BASELINE_FILE
#include <assert.h>
int main(void) {
    void* address=(void*)0x7fffffe00000UL;
    assert(mmap(address,4096,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0)==address);
    memset(address,0,4096);
    commpage_setup(true);
    return *(unsigned char*)0x7fffffe00035UL == 0 ? 12 : 0;
}
