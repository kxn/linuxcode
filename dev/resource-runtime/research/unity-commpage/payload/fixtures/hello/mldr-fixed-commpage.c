/* Exercise actual mmap/mremap and the production stack-switch assembly.
 * Only /proc/self/maps is supplied by the fixture to force each collision. */
#define main linuxcode_unused_mldr_main
#include MLDR_SOURCE_FILE
#undef main
#include <assert.h>
#include <sys/wait.h>

static int collision_kind;
static FILE* fixture_maps(const char* path, const char* mode) {
    assert(strcmp(path, "/proc/self/maps") == 0);
    (void)mode;
    static char maps[256];
    snprintf(maps, sizeof(maps), "%lx-%lx rw-p 00000000 00:00 0 %s\n",
        (unsigned long)0x7fffffe00000UL, (unsigned long)0x7fffffe02000UL,
        (collision_kind == 1 || collision_kind == 3) ? "[stack]" : "/unrelated-image");
    return fmemopen(maps, strlen(maps), "r");
}
#define fopen fixture_maps
#include COMMPAGE_SOURCE_FILE
#undef fopen

static uintptr_t expected_sp;
static void __attribute__((naked,noreturn)) entered(void) {
    __asm__("mov %rsp, %rdi\n jmp verify_entered");
}
void __attribute__((used,noreturn)) verify_entered(uintptr_t sp) {
    assert(sp == expected_sp);
    assert(*(unsigned long*)sp == 0x12345678UL);
    assert(strcmp((char*)0x7fffffe00000UL, "commpage 64-bit") == 0);
    assert(*(unsigned char*)0x7fffffe00035UL > 0);
    assert(*(unsigned char*)0x7fffffe00036UL > 0);
    assert(!pending_commpage);
    _exit(0);
}

static void run_case(int kind) {
    collision_kind = kind;
    const size_t length = 4096;
    void* address = (void*)0x7fffffe00000UL;
    if (kind) {
        assert(mmap(address, length, PROT_READ|PROT_WRITE,
            MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE, -1, 0) == address);
        memset(address, 0xa5, length);
    }
    /* Kind 3 marks argc inside the page and must be refused. */
    commpage_set_initial_stack((void*)(0x7fffffe00000UL + (kind == 3 ? 128 : 8192)));
    commpage_setup(true);
    if (kind) {
        assert(kind == 1 && pending_commpage);
        for (size_t i=0; i<length; ++i) assert(((unsigned char*)address)[i] == 0xa5);
    }
    void* stack = mmap(NULL, 65536, PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    assert(stack != MAP_FAILED);
    expected_sp = ((uintptr_t)stack + 65536 - 128) & ~15UL;
    *(unsigned long*)expected_sp = 0x12345678UL;
    struct load_results lr = {.stack_top=expected_sp, .entry_point=(uintptr_t)entered};
    start_thread(&lr);
    abort();
}
int main(void) {
    for (int kind=0; kind<4; ++kind) {
        pid_t pid=fork(); assert(pid>=0);
        if (!pid) run_case(kind);
        int status; assert(waitpid(pid,&status,0)==pid);
        assert(WIFEXITED(status));
        assert(WEXITSTATUS(status) == (kind>=2 ? 1 : 0));
    }
    puts("MLDR_COMMPAGE_OK free_address retired_stack foreign_mapping live_arguments exact_entry_stack");
    return 0;
}
