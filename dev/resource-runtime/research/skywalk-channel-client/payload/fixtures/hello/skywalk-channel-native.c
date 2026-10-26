#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <skywalk/os_channel.h>
#define CHECK(x) do { if (!(x)) { printf("FAILED line=%d errno=%d %s\n", __LINE__, errno, #x); return 1; } } while (0)
static uint32_t fold(uint64_t sum) { while (sum >> 16) sum = (sum & 65535) + (sum >> 16); return (uint32_t)sum; }
int main(void) {
    setbuf(stdout, NULL);
    void *h = dlopen("/usr/lib/system/libsystem_kernel.dylib", RTLD_LAZY | RTLD_LOCAL); CHECK(h);
#define LOAD(name) __typeof__(&name) name##_fn = dlsym(h, #name); CHECK(name##_fn)
    LOAD(os_channel_attr_create); LOAD(os_channel_attr_clone); LOAD(os_channel_attr_destroy);
    LOAD(os_channel_attr_set); LOAD(os_channel_attr_get); LOAD(os_channel_create_extended);
    const char *required[] = {"os_channel_advance_slot", "os_channel_get_fd", "os_channel_get_next_slot",
        "os_channel_ring_id", "os_channel_rx_ring", "os_channel_set_slot_properties", "os_channel_sync",
        "os_channel_tx_ring", "os_channel_read_attr"};
    for (unsigned i = 0; i < sizeof(required) / sizeof(*required); ++i) CHECK(dlsym(h, required[i]));
    channel_attr_t a = os_channel_attr_create_fn(); CHECK(a);
    uint64_t value = UINT64_MAX;
    CHECK(os_channel_attr_get_fn(a, CHANNEL_ATTR_TX_RINGS, &value) == 0 && value == 0);
    CHECK(os_channel_attr_set_fn(a, CHANNEL_ATTR_EXCLUSIVE, 1) == 0);
    CHECK(os_channel_attr_get_fn(a, CHANNEL_ATTR_EXCLUSIVE, &value) == 0 && value == 1);
    CHECK(os_channel_attr_set_fn(a, CHANNEL_ATTR_TX_LOWAT_UNIT, CHANNEL_THRESHOLD_UNIT_BYTES) == 0);
    CHECK(os_channel_attr_set_fn(a, CHANNEL_ATTR_TX_LOWAT_VALUE, 65537) == 0);
    CHECK(os_channel_attr_get_fn(a, CHANNEL_ATTR_TX_LOWAT_VALUE, &value) == 0 && value == 65537);
    CHECK(os_channel_attr_set_fn(a, CHANNEL_ATTR_TX_RINGS, 4) == ENOTSUP);
    CHECK(os_channel_attr_set_fn(a, CHANNEL_ATTR_TX_LOWAT_UNIT, UINT64_MAX) == EINVAL);
    CHECK(os_channel_attr_get_fn(a, (channel_attr_type_t)9999, &value) == EINVAL);
    channel_attr_t b = os_channel_attr_clone_fn(a); CHECK(b && b != a);
    CHECK(os_channel_attr_get_fn(b, CHANNEL_ATTR_TX_LOWAT_VALUE, &value) == 0 && value == 65537);
    CHECK(os_channel_attr_set_fn(a, CHANNEL_ATTR_TX_LOWAT_VALUE, 2) == 0);
    CHECK(os_channel_attr_get_fn(b, CHANNEL_ATTR_TX_LOWAT_VALUE, &value) == 0 && value == 65537);
    uuid_t uuid = {1}; errno = 0;
    CHECK(os_channel_create_extended_fn(uuid, 1, CHANNEL_DIR_TX_RX, CHANNEL_RING_ID_ANY, b) == NULL && errno == ENOTSUP);
    errno = 0; CHECK(os_channel_create_extended_fn(uuid, 1, (ring_dir_t)999, CHANNEL_RING_ID_ANY, b) == NULL && errno == EINVAL);
    os_channel_attr_destroy_fn(a); os_channel_attr_destroy_fn(b);
    uint32_t (*copy_sum)(const void *, void *, uint32_t, uint32_t) = dlsym(h, "os_cpu_copy_in_cksum"); CHECK(copy_sum);
    unsigned char source[1100], dest[1100];
    for (unsigned i = 0; i < sizeof(source); ++i) source[i] = (unsigned char)(i * 47 + i / 3);
    unsigned checks = 0;
    for (unsigned off = 0; off < 16; ++off) for (unsigned n = 0; n <= 1024; ++n) {
        uint64_t expected = 0x12345678;
        for (unsigned i = 0; i < n; i += 2) expected += source[off + i] | (i + 1 < n ? (unsigned)source[off + i + 1] << 8 : 0);
        memset(dest, 0xab, sizeof(dest));
        uint32_t actual = copy_sum(source + off, dest + off, n, 0x12345678);
        CHECK(fold(actual) == fold(expected)); CHECK(memcmp(source + off, dest + off, n) == 0);
        CHECK(dest[off + n] == 0xab); if (off) CHECK(dest[off - 1] == 0xab); ++checks;
    }
    printf("SKYWALK_REAL_ATTRIBUTES_CLONE_CHECKSUM_AND_UNSUPPORTED_TRANSPORT_OK checks=%u\n", checks);
    return 0;
}
