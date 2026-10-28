#include <libunwind.h>
#include <mach-o/loader.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>

// Public dyld source defines this SPI; compare its results with the loaded
// Mach-O section commands, without relying on ImageLoader private layouts.
struct dyld_unwind_sections {
    const mach_header* mh;
    const void* dwarf_section;
    uintptr_t dwarf_section_length;
    const void* compact_unwind_section;
    uintptr_t compact_unwind_section_length;
};
extern "C" bool _dyld_find_unwind_sections(void*, dyld_unwind_sections*);

static int verify_sections(uintptr_t ip) {
    dyld_unwind_sections info = {};
    if (!_dyld_find_unwind_sections((void*)ip, &info))
        return 30;
    if (!info.mh || info.mh->magic != MH_MAGIC_64)
        return 1;
    const auto* mh = (const mach_header_64*)info.mh;
    if (mh->ncmds > 10000 || mh->sizeofcmds > 16 * 1024 * 1024)
        return 2;
    const unsigned char* start = (const unsigned char*)(mh + 1);
    const unsigned char* end = start + mh->sizeofcmds;
    intptr_t slide = 0;
    for (const unsigned char* at = start; at < end;) {
        const auto* command = (const load_command*)at;
        if (end - at < 8 || command->cmdsize < 8 || command->cmdsize > end - at)
            return 3;
        if (command->cmd == LC_SEGMENT_64) {
            const auto* segment = (const segment_command_64*)at;
            if (!strcmp(segment->segname, "__TEXT"))
                slide = (intptr_t)mh - segment->vmaddr;
        }
        at += command->cmdsize;
    }
    uintptr_t dwarf = 0, dwarf_size = 0, compact = 0, compact_size = 0;
    for (const unsigned char* at = start; at < end;) {
        const auto* command = (const load_command*)at;
        if (command->cmd == LC_SEGMENT_64) {
            const auto* segment = (const segment_command_64*)at;
            if (command->cmdsize < sizeof(*segment) ||
                segment->nsects > (command->cmdsize - sizeof(*segment)) / sizeof(section_64))
                return 4;
            const auto* sections = (const section_64*)(segment + 1);
            for (unsigned i = 0; i < segment->nsects; ++i) {
                const auto& section = sections[i];
                if (!strcmp(section.sectname, "__eh_frame")) {
                    dwarf = section.addr + slide; dwarf_size = section.size;
                }
                if (!strcmp(section.sectname, "__unwind_info")) {
                    compact = section.addr + slide; compact_size = section.size;
                }
            }
        }
        at += command->cmdsize;
    }
    if ((uintptr_t)info.dwarf_section != dwarf || info.dwarf_section_length != dwarf_size ||
        (uintptr_t)info.compact_unwind_section != compact || info.compact_unwind_section_length != compact_size)
        return 5;
    return 0;
}

static __attribute__((noinline)) int inspect_stack(int depth) {
    volatile int remaining = depth;
    if (remaining)
        return inspect_stack(remaining - 1);
    unw_context_t context;
    unw_cursor_t cursor;
    if (unw_getcontext(&context) || unw_init_local(&cursor, &context))
        return 10;
    unsigned frames = 0;
    do {
        unw_word_t ip = 0;
        if (unw_get_reg(&cursor, UNW_REG_IP, &ip))
            return 11;
        if (ip) {
            int status = verify_sections(ip);
            printf("UNWIND_SECTION_STATUS frame=%u status=%d\n", frames, status);
            if (status == 30 && frames >= 4)
                break; // The final native ELF startup frame has no Mach-O image.
            if (status)
                return 12;
        }
        ++frames;
        int status = unw_step(&cursor);
        if (status < 0)
            return 13;
        if (!status)
            break;
    } while (frames < 32);
    printf("UNWIND_STATIC_FRAMES %u\n", frames);
    return frames >= 4 ? 0 : 14;
}

int main() {
    puts("UNWIND_SECTIONS_BEGIN");
    void* anonymous = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (anonymous == MAP_FAILED)
        return 20;
    dyld_unwind_sections info;
    memset(&info, 0xa5, sizeof(info));
    bool found = _dyld_find_unwind_sections(anonymous, &info);
    munmap(anonymous, 4096);
    printf("UNWIND_ANONYMOUS_RECOGNIZED %d\n", found);
    if (found)
        return 21;
    int status = inspect_stack(3);
    if (!status)
        puts("UNWIND_SECTIONS_AND_STATIC_WALK_OK");
    return status;
}
