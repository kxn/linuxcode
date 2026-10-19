#ifndef LINUXCODE_MEMORY_ENTRY_TEST_UTILS_H
#define LINUXCODE_MEMORY_ENTRY_TEST_UTILS_H
#include <dirent.h>

static unsigned long server_pid(void) {
    DIR *proc = opendir("/Volumes/SystemRoot/proc"); assert(proc);
    struct dirent *item;
    unsigned long result = 0;
    while ((item = readdir(proc))) {
        char *end;
        unsigned long pid = strtoul(item->d_name, &end, 10);
        if (!pid || *end) continue;
        char path[256], name[64] = {0};
        snprintf(path, sizeof(path), "/Volumes/SystemRoot/proc/%lu/comm", pid);
        FILE *file = fopen(path, "r");
        if (!file) continue;
        fgets(name, sizeof(name), file); fclose(file);
        if (!strcmp(name, "darlingserver\n")) { result = pid; break; }
    }
    closedir(proc); assert(result); return result;
}
static unsigned backing_files(unsigned long pid) {
    char directory[256];
    snprintf(directory, sizeof(directory), "/Volumes/SystemRoot/proc/%lu/fd", pid);
    DIR *fd = opendir(directory); assert(fd);
    unsigned count = 0;
    struct dirent *item;
    while ((item = readdir(fd))) {
        char path[512], target[512];
        snprintf(path, sizeof(path), "%s/%s", directory, item->d_name);
        ssize_t size = readlink(path, target, sizeof(target) - 1);
        if (size < 0) continue;
        target[size] = 0;
        if (strstr(target, "memfd:darling-memory-entry")) ++count;
    }
    closedir(fd); return count;
}
static void wait_for_backing_count(unsigned long pid, unsigned expected) {
    for (unsigned i = 0; i < 100; ++i) {
        // The existing client has a direct Linux self-unmap fast path. A
        // subsequent VM request reconciles metadata with the actual maps.
        memory_object_size_t size = 4096;
        mach_port_t ignored = MACH_PORT_NULL;
        assert(mach_make_memory_entry_64(mach_task_self(), &size, 0,
            VM_PROT_READ | VM_PROT_IS_MASK, &ignored, MACH_PORT_NULL) == KERN_INVALID_ADDRESS);
        if (backing_files(pid) == expected) return;
        usleep(10000);
    }
    fprintf(stderr, "Backing file leak: actual=%u expected=%u\n", backing_files(pid), expected);
    abort();
}
#endif
