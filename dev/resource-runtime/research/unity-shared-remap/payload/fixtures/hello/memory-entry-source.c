#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <mach/memory_object_types.h>
#include <pthread.h>
#include <servers/bootstrap.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

enum { page = 4096 };
static mach_vm_address_t allocate(size_t size) {
    mach_vm_address_t address = 0;
    assert(mach_vm_allocate(mach_task_self(), &address, size, VM_FLAGS_ANYWHERE) == KERN_SUCCESS);
    return address;
}
static mach_port_t entry_for(mach_vm_address_t address, size_t length, vm_prot_t protection) {
    mach_port_t entry = MACH_PORT_NULL;
    memory_object_size_t size = length;
    kern_return_t status = mach_make_memory_entry_64(mach_task_self(), &size, address,
        protection | VM_PROT_IS_MASK | MAP_MEM_VM_SHARE, &entry, MACH_PORT_NULL);
    if (status != KERN_SUCCESS) fprintf(stderr, "Entry creation failed: address=%#llx length=%zu protection=%u status=%d\n", address, length, protection, status);
    assert(status == KERN_SUCCESS);
    assert(size == ((length + page - 1) & ~(page - 1)) && MACH_PORT_VALID(entry));
    mach_port_urefs_t refs;
    assert(mach_port_get_refs(mach_task_self(), entry, MACH_PORT_RIGHT_SEND, &refs) == KERN_SUCCESS && refs == 1);
    return entry;
}
static mach_vm_address_t map(mach_port_t entry, size_t length, size_t offset, vm_prot_t protection) {
    mach_vm_address_t address = 0;
    assert(mach_vm_map(mach_task_self(), &address, length, 0, VM_FLAGS_ANYWHERE,
        entry, offset, FALSE, protection, protection, VM_INHERIT_NONE) == KERN_SUCCESS);
    assert(address && !(address & (page - 1)));
    return address;
}
static void unmap(mach_vm_address_t address, size_t length) {
    assert(mach_vm_deallocate(mach_task_self(), address, length) == KERN_SUCCESS);
}
static void release(mach_port_t entry) {
    assert(mach_port_deallocate(mach_task_self(), entry) == KERN_SUCCESS);
}
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
        // Self-task unmaps are optimized in the old client. A subsequent VM
        // request reconciles the server's records with the actual mappings.
        memory_object_size_t size = page;
        mach_port_t ignored = MACH_PORT_NULL;
        assert(mach_make_memory_entry_64(mach_task_self(), &size, 0,
            VM_PROT_READ | VM_PROT_IS_MASK, &ignored, MACH_PORT_NULL) == KERN_INVALID_ADDRESS);
        if (backing_files(pid) == expected) return;
        usleep(10000);
    }
    fprintf(stderr, "Backing file leak: actual=%u expected=%u\n", backing_files(pid), expected);
    abort();
}
static void local_cases(void) {
    mach_vm_address_t original = allocate(3 * page);
    unsigned char *bytes = (void *)original;
    memset(bytes, 0x11, 3 * page);
    bytes[page] = 0x22; bytes[2 * page] = 0x33;
    mach_port_t full = entry_for(original, 3 * page, VM_PROT_READ | VM_PROT_WRITE);
    mach_vm_address_t alias = map(full, 3 * page, 0, VM_PROT_READ | VM_PROT_WRITE);
    assert(alias != original);
    ((unsigned char *)alias)[19] = 0x78; assert(bytes[19] == 0x78);
    bytes[27] = 0x56; assert(((unsigned char *)alias)[27] == 0x56);
    mach_port_t middle = entry_for(original + page, page, VM_PROT_READ | VM_PROT_WRITE);
    mach_vm_address_t middle_alias = map(middle, page, 0, VM_PROT_READ | VM_PROT_WRITE);
    assert(*(unsigned char *)middle_alias == 0x22);
    unmap(original + page, page); // Split the source mapping's tracking record.
    mach_port_t left = entry_for(original, page, VM_PROT_READ | VM_PROT_WRITE);
    mach_port_t right = entry_for(original + 2 * page, page, VM_PROT_READ | VM_PROT_WRITE);
    mach_vm_address_t right_alias = map(right, page, 0, VM_PROT_READ | VM_PROT_WRITE);
    assert(*(unsigned char *)right_alias == 0x33);
    *(unsigned char *)right_alias = 0x44; assert(bytes[2 * page] == 0x44);
    mach_port_t invalid = MACH_PORT_NULL;
    memory_object_size_t length = page;
    kern_return_t invalid_result = mach_make_memory_entry_64(mach_task_self(), &length, 0,
        VM_PROT_READ | VM_PROT_IS_MASK, &invalid, MACH_PORT_NULL);
    assert(invalid_result == KERN_INVALID_ADDRESS);
    assert(!invalid);
    mach_port_t readonly = entry_for(alias, page, VM_PROT_READ);
    mach_vm_address_t denied = 0;
    assert(mach_vm_map(mach_task_self(), &denied, page, 0, VM_FLAGS_ANYWHERE,
        readonly, 0, FALSE, VM_PROT_READ | VM_PROT_WRITE,
        VM_PROT_READ | VM_PROT_WRITE, VM_INHERIT_NONE) == KERN_PROTECTION_FAILURE && denied == 0);
    mach_vm_address_t read_alias = map(readonly, page, 0, VM_PROT_READ);
    assert(((unsigned char *)read_alias)[19] == 0x78);
    // Native libxpc asks for RW|IS_MASK: the resulting mapping must use
    // the intersection with this read-only memory-entry capability.
    mach_vm_address_t masked = map(readonly, page, 0,
        VM_PROT_READ | VM_PROT_WRITE | VM_PROT_IS_MASK);
    assert(((unsigned char *)masked)[19] == 0x78);
    errno = 0;
    assert(mprotect((void *)masked, page, PROT_READ | PROT_WRITE) == -1);
    assert(errno == EACCES || errno == EPERM);
    unmap(masked, page);
    masked = 0;
    assert(mach_vm_map(mach_task_self(), &masked, page, 0, VM_FLAGS_ANYWHERE,
        readonly, 0, FALSE, VM_PROT_READ | VM_PROT_WRITE | VM_PROT_IS_MASK,
        VM_PROT_READ, VM_INHERIT_NONE) == KERN_SUCCESS);
    assert(((unsigned char *)masked)[19] == 0x78);
    errno = 0;
    assert(mprotect((void *)masked, page, PROT_READ | PROT_WRITE) == -1);
    assert(errno == EACCES || errno == EPERM);
    unmap(masked, page);
    assert(mach_vm_map(mach_task_self(), &denied, page, 0, VM_FLAGS_ANYWHERE,
        readonly, 0, FALSE, VM_PROT_READ | 0x100,
        VM_PROT_READ | 0x100, VM_INHERIT_NONE) == KERN_INVALID_ARGUMENT && !denied);
    errno = 0;
    assert(mprotect((void *)read_alias, page, PROT_READ | PROT_WRITE) == -1);
    assert(errno == EACCES || errno == EPERM);
    // Capability bounds are enforced by the actual map operation.
    assert(mach_vm_map(mach_task_self(), &denied, 2 * page, 0, VM_FLAGS_ANYWHERE,
        readonly, 0, FALSE, VM_PROT_READ, VM_PROT_READ, VM_INHERIT_NONE) == KERN_INVALID_ARGUMENT);
    release(full); release(middle); release(left); release(right); release(readonly);
    // Closing the capability does not revoke an independently held mapping.
    ((unsigned char *)middle_alias)[3] = 0xab; assert(((unsigned char *)alias)[page + 3] == 0xab);
    unmap(read_alias, page); unmap(right_alias, page); unmap(middle_alias, page);
    unmap(alias, 3 * page); unmap(original, page); unmap(original + 2 * page, page);
}

static void reused_address(void) {
    mach_vm_address_t original = allocate(page);
    memset((void *)original, 0x24, page);
    mach_port_t old = entry_for(original, page, VM_PROT_READ | VM_PROT_WRITE);
    mach_vm_address_t old_alias = map(old, page, 0, VM_PROT_READ | VM_PROT_WRITE);
    assert(!munmap((void *)original, page));
    assert(mmap((void *)original, page, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) == (void *)original);
    memset((void *)original, 0x92, page);
    mach_port_t fresh = entry_for(original, page, VM_PROT_READ | VM_PROT_WRITE);
    mach_vm_address_t fresh_alias = map(fresh, page, 0, VM_PROT_READ | VM_PROT_WRITE);
    assert(*(unsigned char *)old_alias == 0x24 && *(unsigned char *)fresh_alias == 0x92);
    *(unsigned char *)fresh_alias = 0xa7;
    assert(*(unsigned char *)original == 0xa7 && *(unsigned char *)old_alias == 0x24);
    release(old); release(fresh);
    unmap(original, page); unmap(old_alias, page); unmap(fresh_alias, page);
}

static void negative_cases(void) {
    mach_vm_address_t original = allocate(page);
    mach_port_t parent = entry_for(original, page, VM_PROT_READ | VM_PROT_WRITE);
    memory_object_size_t sizes[] = {0, UINT64_MAX};
    for (unsigned i = 0; i < 2; ++i) {
        mach_port_t output = MACH_PORT_NULL;
        assert(mach_make_memory_entry_64(mach_task_self(), &sizes[i], original,
            VM_PROT_READ, &output, MACH_PORT_NULL) == KERN_INVALID_ARGUMENT && !output);
    }
    memory_object_size_t size = page; mach_port_t output = MACH_PORT_NULL;
    assert(mach_make_memory_entry_64(mach_task_self(), &size, original + 1,
        VM_PROT_READ, &output, MACH_PORT_NULL) == KERN_INVALID_ARGUMENT && !output);
    assert(mach_make_memory_entry_64(mach_task_self(), &size, original,
        VM_PROT_READ | MAP_MEM_VM_COPY, &output, MACH_PORT_NULL) == KERN_NOT_SUPPORTED && !output);
    assert(mach_make_memory_entry_64(mach_task_self(), &size, original,
        VM_PROT_READ, &output, parent) == KERN_NOT_SUPPORTED && !output);
    void *preexisting_shared = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    assert(preexisting_shared != MAP_FAILED);
    memset(preexisting_shared, 0x5c, page);
    assert(mach_make_memory_entry_64(mach_task_self(), &size, (mach_vm_address_t)preexisting_shared,
        VM_PROT_READ, &output, MACH_PORT_NULL) == KERN_NOT_SUPPORTED && !output);
    assert(*(unsigned char *)preexisting_shared == 0x5c);
    assert(!munmap(preexisting_shared, page));
    mach_vm_address_t mapped = 0;
    assert(mach_vm_map(mach_task_self(), &mapped, page, 0, VM_FLAGS_ANYWHERE,
        parent, 0, TRUE, VM_PROT_READ, VM_PROT_READ, VM_INHERIT_NONE) == KERN_NOT_SUPPORTED && !mapped);
    assert(mach_vm_map(mach_task_self(), &mapped, page, page-1, VM_FLAGS_ANYWHERE,
        parent, 0, FALSE, VM_PROT_READ, VM_PROT_READ, VM_INHERIT_NONE) == KERN_NOT_SUPPORTED && !mapped);
    assert(mach_vm_map(mach_task_self(), &mapped, page, 0, VM_FLAGS_ANYWHERE,
        parent, 1, FALSE, VM_PROT_READ, VM_PROT_READ, VM_INHERIT_NONE) == KERN_INVALID_ARGUMENT && !mapped);
    assert(mach_vm_map(mach_task_self(), &mapped, page, 0, VM_FLAGS_ANYWHERE,
        parent, 0, FALSE, VM_PROT_WRITE, VM_PROT_READ, VM_INHERIT_NONE) == KERN_INVALID_ARGUMENT && !mapped);
    mach_port_t wrong;
    assert(mach_port_allocate(mach_task_self(), MACH_PORT_RIGHT_RECEIVE, &wrong) == KERN_SUCCESS);
    assert(mach_port_insert_right(mach_task_self(), wrong, wrong, MACH_MSG_TYPE_MAKE_SEND) == KERN_SUCCESS);
    assert(mach_vm_map(mach_task_self(), &mapped, page, 0, VM_FLAGS_ANYWHERE,
        wrong, 0, FALSE, VM_PROT_READ, VM_PROT_READ, VM_INHERIT_NONE) == KERN_INVALID_ARGUMENT && !mapped);
    assert(mach_port_destroy(mach_task_self(), wrong) == KERN_SUCCESS);
    release(parent); unmap(original, page);
}

struct worker_context { mach_port_t entry; unsigned index; };
static void *map_worker(void *opaque) {
    struct worker_context *worker = opaque;
    for (unsigned i = 0; i < 8; ++i) {
        mach_vm_address_t alias = map(worker->entry, page, 0, VM_PROT_READ | VM_PROT_WRITE);
        ((unsigned char *)alias)[worker->index] = (unsigned char)(0x80 + i);
        unmap(alias, page);
    }
    return NULL;
}
static void concurrent_maps(void) {
    mach_vm_address_t original = allocate(page);
    mach_port_t entry = entry_for(original, page, VM_PROT_READ | VM_PROT_WRITE);
    pthread_t threads[4]; struct worker_context workers[4];
    for (unsigned i = 0; i < 4; ++i) {
        workers[i] = (struct worker_context){entry, i};
        assert(!pthread_create(&threads[i], NULL, map_worker, &workers[i]));
    }
    for (unsigned i = 0; i < 4; ++i) {
        assert(!pthread_join(threads[i], NULL));
        assert(((unsigned char *)original)[i] == 0x87);
    }
    mach_port_urefs_t refs;
    assert(mach_port_get_refs(mach_task_self(), entry, MACH_PORT_RIGHT_SEND, &refs) == KERN_SUCCESS && refs == 1);
    release(entry); unmap(original, page);
}
struct capability_message {
    mach_msg_header_t head;
    mach_msg_body_t body;
    mach_msg_port_descriptor_t entry;
};
union incoming { struct capability_message message; unsigned char bytes[512]; };
static void receive(mach_port_t port, union incoming *message) {
    memset(message, 0, sizeof(*message));
    assert(mach_msg(&message->message.head, MACH_RCV_MSG | MACH_RCV_TIMEOUT,
        0, sizeof(*message), port, 5000, MACH_PORT_NULL) == MACH_MSG_SUCCESS);
}
static void send_header(mach_port_t remote, mach_port_t local, unsigned disposition, int id) {
    mach_msg_header_t message = {0};
    message.msgh_bits = MACH_MSGH_BITS(disposition, local ? MACH_MSG_TYPE_MAKE_SEND_ONCE : 0);
    message.msgh_remote_port = remote; message.msgh_local_port = local;
    message.msgh_id = id; message.msgh_size = sizeof(message);
    assert(mach_msg(&message, MACH_SEND_MSG | MACH_SEND_TIMEOUT,
        sizeof(message), 0, MACH_PORT_NULL, 5000, MACH_PORT_NULL) == MACH_MSG_SUCCESS);
}
static void interprocess(void) {
    const char *service = "org.linuxcode.memory-entry-probe";
    mach_port_t receiver;
    assert(mach_port_allocate(mach_task_self(), MACH_PORT_RIGHT_RECEIVE, &receiver) == KERN_SUCCESS);
    assert(mach_port_insert_right(mach_task_self(), receiver, receiver, MACH_MSG_TYPE_MAKE_SEND) == KERN_SUCCESS);
    assert(bootstrap_register(bootstrap_port, (char *)service, receiver) == KERN_SUCCESS);
    mach_vm_address_t original = allocate(page);
    memset((void *)original, 0x32, page);
    mach_port_t entry = entry_for(original, page, VM_PROT_READ | VM_PROT_WRITE);
    pid_t child = fork(); assert(child >= 0);
    if (!child) {
        mach_port_t server, reply;
        assert(bootstrap_look_up(bootstrap_port, (char *)service, &server) == KERN_SUCCESS);
        assert(mach_port_allocate(mach_task_self(), MACH_PORT_RIGHT_RECEIVE, &reply) == KERN_SUCCESS);
        send_header(server, reply, MACH_MSG_TYPE_COPY_SEND, 0x3341);
        union incoming input; receive(reply, &input);
        assert(input.message.head.msgh_id == 0x3342 && input.message.body.msgh_descriptor_count == 1);
        assert(input.message.entry.disposition == MACH_MSG_TYPE_PORT_SEND);
        mach_port_t transferred = input.message.entry.name;
        mach_vm_address_t address = map(transferred, page, 0, VM_PROT_READ | VM_PROT_WRITE);
        assert(address != original && *(unsigned char *)address == 0x32);
        release(transferred);
        ((unsigned char *)address)[17] = 0xa5;
        send_header(server, reply, MACH_MSG_TYPE_COPY_SEND, 0x3343);
        receive(reply, &input);
        assert(input.message.head.msgh_id == 0x3344);
        assert(((unsigned char *)address)[18] == 0xb6);
        unmap(address, page); release(server);
        assert(mach_port_destroy(mach_task_self(), reply) == KERN_SUCCESS);
        _exit(0);
    }
    union incoming request; receive(receiver, &request);
    assert(request.message.head.msgh_id == 0x3341);
    struct capability_message response = {0};
    response.head.msgh_bits = MACH_MSGH_BITS(MACH_MSG_TYPE_MOVE_SEND_ONCE, 0) | MACH_MSGH_BITS_COMPLEX;
    response.head.msgh_remote_port = request.message.head.msgh_remote_port;
    response.head.msgh_size = sizeof(response); response.head.msgh_id = 0x3342;
    response.body.msgh_descriptor_count = 1; response.entry.name = entry;
    response.entry.disposition = MACH_MSG_TYPE_COPY_SEND; response.entry.type = MACH_MSG_PORT_DESCRIPTOR;
    assert(mach_msg(&response.head, MACH_SEND_MSG | MACH_SEND_TIMEOUT, sizeof(response), 0,
        MACH_PORT_NULL, 5000, MACH_PORT_NULL) == MACH_MSG_SUCCESS);
    release(entry);
    receive(receiver, &request); assert(request.message.head.msgh_id == 0x3343);
    assert(((unsigned char *)original)[17] == 0xa5);
    ((unsigned char *)original)[18] = 0xb6;
    send_header(request.message.head.msgh_remote_port, MACH_PORT_NULL, MACH_MSG_TYPE_MOVE_SEND_ONCE, 0x3344);
    int status; assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    unmap(original, page);
    assert(mach_port_destroy(mach_task_self(), receiver) == KERN_SUCCESS);
}
int main(void) {
    setbuf(stdout, NULL);
    unsigned long pid = server_pid(); unsigned baseline = backing_files(pid);
    for (unsigned i = 0; i < 32; ++i) local_cases();
    wait_for_backing_count(pid, baseline);
    puts("MEMORY_ENTRY_SOURCE_ALIAS_SUBRANGE_PARTIAL_UNMAP_READONLY_NO_WRITE_ESCALATION_32_CYCLES_FD_CLEANUP_OK");
    reused_address(); wait_for_backing_count(pid, baseline);
    puts("MEMORY_ENTRY_ADDRESS_REUSE_CLEANUP_OK");
    negative_cases(); wait_for_backing_count(pid, baseline);
    puts("MEMORY_ENTRY_NEGATIVE_CASES_CLEANUP_OK");
    concurrent_maps();
    wait_for_backing_count(pid, baseline);
    puts("MEMORY_ENTRY_SOURCE_ADDRESS_REUSE_INVALID_CAPABILITIES_FLAGS_BOUNDS_AND_32_CONCURRENT_MAPS_OK");
    interprocess();
    wait_for_backing_count(pid, baseline);
    puts("MEMORY_ENTRY_SOURCE_REAL_INTERPROCESS_MACH_CAPABILITY_BIDIRECTIONAL_SHARING_AFTER_PORT_RELEASE_OK");
    return 0;
}
