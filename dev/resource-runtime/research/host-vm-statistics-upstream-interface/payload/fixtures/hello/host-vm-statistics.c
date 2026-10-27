#include <mach/mach.h>
#include <mach/host_info.h>
#include <mach/vm_statistics.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysctl.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "HOST_VM_FAIL line=%d\n", __LINE__); return 1; } ++checks; } while (0)

int main(int argc, char** argv) {
    unsigned checks = 0;
    setbuf(stdout, NULL);
    host_t host = mach_host_self();
    vm_size_t page_size = 0;
    CHECK(host_page_size(host, &page_size) == KERN_SUCCESS && page_size > 0);
    uint64_t total = 0;
    size_t size = sizeof(total);
    CHECK(sysctlbyname("hw.memsize", &total, &size, NULL, 0) == 0 && total > 0);
    vm_statistics64_data_t initial;
    mach_msg_type_number_t count = HOST_VM_INFO64_COUNT;
    CHECK(host_statistics64(host, HOST_VM_INFO64, (host_info64_t)&initial, &count) == KERN_SUCCESS);
    printf("HOST_VM_SAMPLE %llu %llu %u %u %u %u\n", (unsigned long long)page_size,
           (unsigned long long)total, initial.free_count, initial.active_count, initial.inactive_count, initial.wire_count);
    if (argc > 1 && !strcmp(argv[1], "baseline")) {
        CHECK(initial.free_count == 0 && initial.active_count == 0 && initial.inactive_count == 0 && initial.wire_count == 0);
        puts("HOST_VM_ZERO_STUB_REPRODUCED");
        return 0;
    }
    CHECK(initial.free_count + (uint64_t)initial.active_count + initial.inactive_count > 0);
    CHECK(((uint64_t)initial.active_count + initial.wire_count) * page_size > 0);
    CHECK(((uint64_t)initial.active_count + initial.wire_count) * page_size <= total);

    // Exercise both ABIs through real Mach messages, including historical and
    // oversized counts. The kernel must not clear bytes beyond its reply.
    for (int wide = 0; wide != 2; ++wide) {
        unsigned latest = wide ? HOST_VM_INFO64_COUNT : HOST_VM_INFO_COUNT;
        unsigned oldest = wide ? HOST_VM_INFO64_REV0_COUNT : HOST_VM_INFO_REV0_COUNT;
        for (unsigned requested = 0; requested <= latest + 4; ++requested) {
            union { uint64_t alignment; unsigned char bytes[512]; } buffer;
            memset(&buffer, 0xa5, sizeof(buffer));
            count = requested;
            kern_return_t status = wide ?
                host_statistics64(host, HOST_VM_INFO64, (host_info64_t)buffer.bytes, &count) :
                host_statistics(host, HOST_VM_INFO, (host_info_t)buffer.bytes, &count);
            unsigned written = 0;
            if (requested < oldest) {
                CHECK(status == KERN_FAILURE && count == requested);
            } else {
                // This Darling/XNU baseline implements through VM64 rev1.
                // Newer SDK headers also declare swapped/tag-storage fields;
                // an older kernel correctly returns its supported revision.
                unsigned expected = wide ? HOST_VM_INFO64_REV1_COUNT : latest;
                if (wide) {
                    if (requested < HOST_VM_INFO64_REV1_COUNT) expected = HOST_VM_INFO64_REV0_COUNT;
                } else {
                    if (requested < HOST_VM_INFO_REV1_COUNT) expected = HOST_VM_INFO_REV0_COUNT;
                    else if (requested < HOST_VM_INFO_REV2_COUNT) expected = HOST_VM_INFO_REV1_COUNT;
                }
                if (status != KERN_SUCCESS || count != expected)
                    fprintf(stderr, "HOST_VM_REPLY wide=%d requested=%u status=%d count=%u expected=%u\n", wide, requested, status, count, expected);
                CHECK(status == KERN_SUCCESS && count == expected);
                written = count * sizeof(integer_t);
                natural_t* pages = (natural_t*)buffer.bytes;
                CHECK((uint64_t)pages[0] + pages[1] + pages[2] > 0);
            }
            for (unsigned i = written; i < sizeof(buffer.bytes); ++i) CHECK(buffer.bytes[i] == 0xa5);
        }
    }
    printf("HOST_VM_REVISION_AND_BUFFER_ABI_OK checks=%u\n", checks);
    return 0;
}
