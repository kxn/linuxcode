#include <darling-config.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/sysctl_net.h>
#include <sys/errno.h>
#include <net/route.h>
#include <sys/socket.h>
#include <net/if.h>
#include <net/if_dl.h>
#include <net/if_types.h>
#include <netinet/in.h>
#include <darling/emulation/linux_premigration/elfcalls_wrapper.h>
#include <darling/emulation/common/simple.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/conversion/fcntl/open.h>
#include <darling/emulation/xnu_syscall/bsd/helper/misc/readline.h>
#include <darling/emulation/xnu_syscall/bsd/impl/network/socket.h>
#include <darling/emulation/xnu_syscall/bsd/impl/ioctl/ioctl.h>
#include <darling/emulation/xnu_syscall/bsd/impl/fcntl/open.h>
#include <darling/emulation/xnu_syscall/bsd/impl/unistd/close.h>

extern void* memset(void*, int, size_t);
extern void* memcpy(void*, const void*, size_t);
extern int strcmp(const char*, const char*);
extern size_t strlen(const char*);
extern size_t strnlen(const char*, size_t);
extern int memcmp(const void*, const void*, size_t);

/* Linux UAPI layouts: ifaddrs.h, linux/if_packet.h, linux/if.h and
 * linux/ethtool.h. Do not include Linux libc headers in a Darwin translation
 * unit. Interface discovery itself is Linux libc's complete getifaddrs,
 * including link-only devices, all addresses and the current network namespace.
 * https://sourceware.org/git/glibc.git (sysdeps/unix/sysv/linux/ifaddrs.c)
 */
struct linux_sockaddr { unsigned short family; unsigned char data[14]; };
struct linux_ifaddrs {
    struct linux_ifaddrs* next;
    char* name;
    unsigned int flags;
    struct linux_sockaddr *address, *netmask, *destination;
    void* data;
};
struct linux_sockaddr_ll {
    unsigned short family, protocol;
    int index;
    unsigned short hardware_type;
    unsigned char packet_type, address_length, address[24];
};
struct linux_ifreq { char name[16]; union { int mtu; void* data; unsigned char padding[24]; }; };
struct linux_ethtool_cmd {
    unsigned int cmd, supported, advertising;
    unsigned short speed;
    unsigned char duplex, port, phy_address, transceiver, autoneg, mdio_support;
    unsigned int maxtxpkt, maxrxpkt;
    unsigned short speed_hi;
    unsigned char eth_tp_mdix, eth_tp_mdix_ctrl;
    unsigned int lp_advertising, reserved[2];
};
struct interface_statistics { uint64_t value[16]; };
struct route_output { char* buffer; unsigned long capacity, used; int short_buffer; };
struct native_interfaces {
    void* libc;
    struct linux_ifaddrs* head;
    void (*release)(struct linux_ifaddrs*);
};

static void close_interfaces(struct native_interfaces* interfaces) {
    if (interfaces->head) interfaces->release(interfaces->head);
    if (interfaces->libc) native_dlclose(interfaces->libc);
}
static int open_interfaces(struct native_interfaces* interfaces) {
    memset(interfaces, 0, sizeof(*interfaces));
    interfaces->libc = native_dlopen("libc.so.6");
    if (!interfaces->libc) return -ENOTSUP;
    int (*get_interfaces)(struct linux_ifaddrs**) = native_dlsym(interfaces->libc, "getifaddrs");
    interfaces->release = native_dlsym(interfaces->libc, "freeifaddrs");
    int* (*native_errno)(void) = native_dlsym(interfaces->libc, "__errno_location");
    if (!get_interfaces || !interfaces->release || !native_errno) return -ENOTSUP;
    return get_interfaces(&interfaces->head) < 0 ? errno_linux_to_bsd(-*native_errno()) : 0;
}

static sysctl_handler(handle_route);
const struct known_sysctl sysctls_net[] = {
    { .oid = 17, .type = CTLTYPE_OPAQUE, .exttype = "", .name = "route", .handler = handle_route },
    { .oid = -1 },
};

static size_t route_alignment(size_t size) { return (size + 3) & ~(size_t)3; }
static int output_message(struct route_output* output, const void* message, size_t length) {
    if (length > (unsigned long)-1 - output->used) return -EOVERFLOW;
    if (output->buffer) {
        if (output->used <= output->capacity && length <= output->capacity - output->used)
            memcpy(output->buffer + output->used, message, length);
        else output->short_buffer = 1;
    }
    output->used += length;
    return 0;
}
static int interface_flags(unsigned int linux_flags) {
    int flags = linux_flags & (IFF_UP | IFF_BROADCAST | IFF_DEBUG | IFF_LOOPBACK |
        IFF_POINTOPOINT | IFF_RUNNING | IFF_NOARP | IFF_PROMISC | IFF_ALLMULTI);
    if (linux_flags & 0x1000) flags |= IFF_MULTICAST;
    return flags;
}
static unsigned char interface_type(unsigned int type) {
    switch (type) {
        case 1: return IFT_ETHER;
        case 772: return IFT_LOOP;
        case 512: return IFT_PPP;
        case 256: return IFT_SLIP;
        case 768: case 769: case 776: case 778: return IFT_GIF;
        default: return IFT_OTHER;
    }
}
/* /proc/net/dev exports the kernel's 64-bit dev_get_stats counters. Unlike
 * getifaddrs.ifa_data (rtnl_link_stats), these do not wrap at 2^32 bytes.
 * https://docs.kernel.org/networking/statistics.html
 */
static int read_statistics(const char* name, struct interface_statistics* stats) {
    int fd = sys_open_nocancel(DARLING_PROCFS_PATH "/net/dev", BSD_O_RDONLY, 0);
    if (fd < 0) return fd;
    struct rdline_buffer buffer; _readline_init(&buffer);
    const char* line; int result = -EAGAIN;
    while ((line = _readline(fd, &buffer))) {
        while (*line == ' ' || *line == '\t') line++;
        size_t length = strlen(name);
        if (strnlen(line, length + 1) < length + 1) continue;
        if (line[length] != ':') continue;
        size_t i; for (i = 0; i < length && line[i] == name[i]; i++);
        if (i != length) continue;
        line += length + 1;
        for (i = 0; i < 16; i++) {
            while (*line == ' ' || *line == '\t') line++;
            if (*line < '0' || *line > '9') break;
            stats->value[i] = __simple_atoi(line, &line);
        }
        result = i == 16 ? 0 : -EIO; break;
    }
    close_internal(fd); return result;
}
static uint64_t interface_speed(int fd, const char* name) {
    struct linux_ethtool_cmd settings; memset(&settings, 0, sizeof(settings));
    settings.cmd = 1; /* ETHTOOL_GSET; Linux returns EOPNOTSUPP for virtual links. */
    struct linux_ifreq request; memset(&request, 0, sizeof(request));
    memcpy(request.name, name, strlen(name)); request.data = &settings;
    if (__real_ioctl(fd, 0x8946, &request) < 0) return 0; /* unknown, not an invented link rate */
    uint32_t speed = ((uint32_t)settings.speed_hi << 16) | settings.speed;
    return speed == UINT32_MAX || speed == UINT16_MAX ? 0 : (uint64_t)speed * 1000000;
}
#define FILL_STATISTICS(data, stats) do { \
    (data).ifi_ibytes = (stats).value[0]; (data).ifi_ipackets = (stats).value[1]; \
    (data).ifi_ierrors = (stats).value[2]; (data).ifi_iqdrops = (stats).value[3]; \
    (data).ifi_imcasts = (stats).value[7]; (data).ifi_obytes = (stats).value[8]; \
    (data).ifi_opackets = (stats).value[9]; (data).ifi_oerrors = (stats).value[10]; \
    (data).ifi_collisions = (stats).value[13]; \
} while (0)

static int output_link(struct route_output* output, int fd,
        const struct linux_ifaddrs* entry, int extended) {
    const struct linux_sockaddr_ll* link = (const void*)entry->address;
    size_t name_length = strnlen(entry->name, 16);
    if (!name_length || name_length == 16 || link->address_length > sizeof(link->address)) return -EINVAL;
    if (link->index <= 0 || link->index > UINT16_MAX) return -EOVERFLOW;
    size_t header_size = extended ? sizeof(struct if_msghdr2) : sizeof(struct if_msghdr);
    size_t address_size = sizeof(struct sockaddr_dl);
    if (name_length + link->address_length > sizeof(((struct sockaddr_dl*)0)->sdl_data))
        address_size += name_length + link->address_length - sizeof(((struct sockaddr_dl*)0)->sdl_data);
    union { struct if_msghdr2 alignment; unsigned char bytes[512]; } message;
    size_t length = header_size + route_alignment(address_size);
    if (length > sizeof(message.bytes) || address_size > UINT8_MAX) return -EOVERFLOW;
    memset(&message, 0, sizeof(message));
    struct linux_ifreq mtu; memset(&mtu, 0, sizeof(mtu)); memcpy(mtu.name, entry->name, name_length);
    int result = __real_ioctl(fd, 0x8921, &mtu); /* SIOCGIFMTU */
    if (result < 0) return result;
    struct interface_statistics stats;
    if ((result = read_statistics(entry->name, &stats)) < 0) return result;
    uint64_t speed = interface_speed(fd, entry->name);
    if (extended) {
        struct if_msghdr2* header = (void*)message.bytes;
        header->ifm_msglen = length; header->ifm_version = RTM_VERSION; header->ifm_type = RTM_IFINFO2;
        header->ifm_addrs = RTA_IFP; header->ifm_flags = interface_flags(entry->flags); header->ifm_index = link->index;
        struct linux_ifreq queue = mtu;
        if (__real_ioctl(fd, 0x8942, &queue) >= 0) header->ifm_snd_maxlen = queue.mtu; /* SIOCGIFTXQLEN */
        header->ifm_data.ifi_type = interface_type(link->hardware_type); header->ifm_data.ifi_addrlen = link->address_length;
        header->ifm_data.ifi_mtu = mtu.mtu; header->ifm_data.ifi_baudrate = speed;
        FILL_STATISTICS(header->ifm_data, stats);
    } else {
        struct if_msghdr* header = (void*)message.bytes;
        header->ifm_msglen = length; header->ifm_version = RTM_VERSION; header->ifm_type = RTM_IFINFO;
        header->ifm_addrs = RTA_IFP; header->ifm_flags = interface_flags(entry->flags); header->ifm_index = link->index;
        header->ifm_data.ifi_type = interface_type(link->hardware_type); header->ifm_data.ifi_addrlen = link->address_length;
        header->ifm_data.ifi_mtu = mtu.mtu; header->ifm_data.ifi_baudrate = speed > UINT32_MAX ? UINT32_MAX : speed;
        FILL_STATISTICS(header->ifm_data, stats);
    }
    struct sockaddr_dl* address = (void*)(message.bytes + header_size);
    address->sdl_len = address_size; address->sdl_family = AF_LINK; address->sdl_index = link->index;
    address->sdl_type = interface_type(link->hardware_type); address->sdl_nlen = name_length; address->sdl_alen = link->address_length;
    memcpy(address->sdl_data, entry->name, name_length); memcpy(LLADDR(address), link->address, link->address_length);
    return output_message(output, message.bytes, length);
}
static void convert_address(void* destination, const struct linux_sockaddr* source, unsigned int index) {
    unsigned char* bytes = destination;
    if (source->family == 2) {
        memcpy(destination, source, sizeof(struct sockaddr_in));
        bytes[0] = sizeof(struct sockaddr_in); bytes[1] = AF_INET;
    } else {
        memcpy(destination, source, sizeof(struct sockaddr_in6));
        bytes[0] = sizeof(struct sockaddr_in6); bytes[1] = AF_INET6;
        /* Linux carries scope_id explicitly. Keep it, rather than inventing an
         * address or applying the legacy embedded-scope convention twice. */
        (void)index;
    }
}
static int output_address(struct route_output* output, const struct linux_ifaddrs* entry, unsigned int index) {
    size_t size = entry->address->family == 2 ? sizeof(struct sockaddr_in) : sizeof(struct sockaddr_in6);
    int has_destination = entry->destination && (entry->flags & (0x2 | 0x10));
    int mask = (entry->netmask ? RTA_NETMASK : 0) | RTA_IFA | (has_destination ? RTA_BRD : 0);
    union { struct ifa_msghdr alignment; unsigned char bytes[128]; } message;
    memset(&message, 0, sizeof(message));
    struct ifa_msghdr* header = (void*)message.bytes;
    header->ifam_version = RTM_VERSION; header->ifam_type = RTM_NEWADDR;
    header->ifam_addrs = mask; header->ifam_index = index;
    size_t used = sizeof(*header);
    if (entry->netmask) { convert_address(message.bytes + used, entry->netmask, index); used += route_alignment(size); }
    convert_address(message.bytes + used, entry->address, index); used += route_alignment(size);
    if (has_destination) { convert_address(message.bytes + used, entry->destination, index); used += route_alignment(size); }
    header->ifam_msglen = used;
    return output_message(output, message.bytes, used);
}
static int do_iflist(void* old, unsigned long* oldlen, int family, unsigned int index, int extended) {
    int result, fd = -1; struct native_interfaces native;
    if ((result = open_interfaces(&native)) < 0) goto out;
    if ((fd = sys_socket(AF_INET, SOCK_DGRAM, 0)) < 0) { result = fd; goto out; }
    struct route_output output = { old, old ? *oldlen : 0, 0, 0 };
    for (struct linux_ifaddrs* link = native.head; link; link = link->next) {
        if (!link->address || link->address->family != 17) continue; /* Linux AF_PACKET */
        unsigned int actual_index = ((struct linux_sockaddr_ll*)link->address)->index;
        if (index && index != actual_index) continue;
        result = output_link(&output, fd, link, extended);
        if (result < 0) goto out;
        for (struct linux_ifaddrs* address = native.head; address; address = address->next) {
            if (!address->address || strcmp(address->name, link->name)) continue;
            int bsd_family = address->address->family == 2 ? AF_INET : address->address->family == 10 ? AF_INET6 : 0;
            if (!bsd_family || (family && family != bsd_family)) continue;
            if ((result = output_address(&output, address, actual_index)) < 0) goto out;
        }
    }
    *oldlen = output.used; result = output.short_buffer ? -ENOMEM : 0;
out:
    if (fd >= 0) close_internal(fd);
    close_interfaces(&native); return result;
}
/* Linux publishes the active namespace's IPv4/IPv6 routing tables through
 * procfs. Translate the real main-table entries to the public XNU route ABI;
 * NET_RT_DUMP is also used by libc/.NET to discover default gateways. */
static int route_field(const char** cursor, const char** value, size_t* length) {
    const char* p = *cursor;
    while (*p == ' ' || *p == '\t') p++;
    *value = p;
    while (*p && *p != ' ' && *p != '\t') p++;
    *length = p - *value; *cursor = p;
    return *length != 0;
}
static int hex_address(const char* text, size_t length, unsigned char* output) {
    if (length != 32) return -EIO;
    for (unsigned i = 0; i < 16; i++) {
        char byte[3] = { text[i * 2], text[i * 2 + 1], 0 };
        const char* end; output[i] = __simple_atoi16(byte, &end);
        if (*end) return -EIO;
    }
    return 0;
}
static unsigned int route_interface_index(const struct native_interfaces* native, const char* name, size_t length) {
    for (const struct linux_ifaddrs* p = native->head; p; p = p->next)
        if (p->address && p->address->family == 17 && strlen(p->name) == length && !memcmp(name, p->name, length))
            return ((const struct linux_sockaddr_ll*)p->address)->index;
    return 0;
}
static int output_route(struct route_output* output, unsigned int index, int family,
        const unsigned char* destination, const unsigned char* gateway,
        const unsigned char* mask, uint32_t linux_flags, uint32_t mtu) {
    if (!index || index > UINT16_MAX) return -EOVERFLOW;
    union { struct rt_msghdr alignment; unsigned char bytes[512]; } message;
    memset(&message, 0, sizeof(message));
    struct rt_msghdr* header = (void*)message.bytes;
    header->rtm_version = RTM_VERSION; header->rtm_type = RTM_GET; header->rtm_index = index;
    header->rtm_flags = linux_flags & (RTF_UP | RTF_GATEWAY | RTF_HOST | RTF_DYNAMIC | RTF_MODIFIED);
    if (linux_flags & 0x200) header->rtm_flags |= RTF_REJECT;
    header->rtm_addrs = RTA_DST | RTA_NETMASK;
    int address_bytes = family == AF_INET ? 4 : 16;
    int has_gateway = 0;
    for (int i = 0; i < address_bytes; i++) has_gateway |= gateway[i];
    if (has_gateway) header->rtm_addrs |= RTA_GATEWAY;
    else header->rtm_flags &= ~RTF_GATEWAY;
    /* Linux route priority is not XNU's "max hops expected" metric. */
    header->rtm_rmx.rmx_mtu = mtu;
    size_t used = sizeof(*header);
    for (int bit = RTA_DST; bit <= RTA_NETMASK; bit <<= 1) {
        if (!(header->rtm_addrs & bit)) continue;
        const unsigned char* value = bit == RTA_DST ? destination : bit == RTA_GATEWAY ? gateway : mask;
        if (family == AF_INET) {
            struct sockaddr_in* address = (void*)(message.bytes + used);
            address->sin_len = sizeof(*address); address->sin_family = AF_INET;
            memcpy(&address->sin_addr, value, 4); used += route_alignment(sizeof(*address));
        } else {
            struct sockaddr_in6* address = (void*)(message.bytes + used);
            address->sin6_len = sizeof(*address); address->sin6_family = AF_INET6;
            memcpy(&address->sin6_addr, value, 16);
            if (value[0] == 0xfe && (value[1] & 0xc0) == 0x80) address->sin6_scope_id = index;
            used += route_alignment(sizeof(*address));
        }
    }
    header->rtm_msglen = used;
    return output_message(output, message.bytes, used);
}
static int read_routes(struct route_output* output, const struct native_interfaces* native, int ipv6) {
    int fd = sys_open_nocancel(ipv6 ? DARLING_PROCFS_PATH "/net/ipv6_route" : DARLING_PROCFS_PATH "/net/route", BSD_O_RDONLY, 0);
    if (fd < 0) {
        /* IPv6 can be disabled in the Linux kernel; IPv4 is still available. */
        return ipv6 && fd == -ENOENT ? 0 : fd;
    }
    struct rdline_buffer buffer; _readline_init(&buffer);
    const char* line; int status = 0;
    if (!ipv6) _readline(fd, &buffer); /* /proc/net/route has a header. */
    while ((line = _readline(fd, &buffer))) {
        const char* fields[11]; size_t lengths[11]; unsigned count = ipv6 ? 10 : 11;
        unsigned i; for (i = 0; i < count && route_field(&line, &fields[i], &lengths[i]); i++);
        if (i != count) { status = -EIO; break; }
        unsigned int index = route_interface_index(native, fields[ipv6 ? 9 : 0], lengths[ipv6 ? 9 : 0]);
        if (!index) { status = -EAGAIN; break; }
        unsigned char destination[16] = {0}, gateway[16] = {0}, mask[16] = {0};
        uint32_t flags, mtu = 0;
        if (ipv6) {
            if ((status = hex_address(fields[0], lengths[0], destination)) < 0 ||
                (status = hex_address(fields[4], lengths[4], gateway)) < 0) break;
            unsigned long long prefix = __simple_atoi16(fields[1], NULL);
            if (prefix > 128) { status = -EIO; break; }
            for (unsigned bit = 0; bit < prefix; bit++) mask[bit / 8] |= 0x80 >> (bit % 8);
            flags = __simple_atoi16(fields[8], NULL);
        } else {
            uint32_t value = __simple_atoi16(fields[1], NULL); memcpy(destination, &value, 4);
            value = __simple_atoi16(fields[2], NULL); memcpy(gateway, &value, 4);
            value = __simple_atoi16(fields[7], NULL); memcpy(mask, &value, 4);
            flags = __simple_atoi16(fields[3], NULL); mtu = __simple_atoi(fields[8], NULL);
        }
        status = output_route(output, index, ipv6 ? AF_INET6 : AF_INET, destination, gateway, mask, flags, mtu);
        if (status < 0) break;
    }
    close_internal(fd); return status;
}
static int do_route_dump(void* old, unsigned long* oldlen, int family) {
    struct native_interfaces native; int result = open_interfaces(&native);
    if (result < 0) { close_interfaces(&native); return result; }
    struct route_output output = {old, old ? *oldlen : 0, 0, 0};
    if (!family || family == AF_INET) result = read_routes(&output, &native, 0);
    if (result >= 0 && (!family || family == AF_INET6)) result = read_routes(&output, &native, 1);
    if (result >= 0) { *oldlen = output.used; result = output.short_buffer ? -ENOMEM : 0; }
    close_interfaces(&native); return result;
}
static sysctl_handler(handle_route) {
    if (nlen != 6 || !oldlen || name[2] != 0 || name[5] < 0) return -EINVAL;
    if (_new || newlen) return -EPERM;
    if (name[3] && name[3] != AF_INET && name[3] != AF_INET6 && name[3] != AF_LINK) return -EAFNOSUPPORT;
    if (name[4] == 1) return do_route_dump(old, oldlen, name[3]);
    if (name[4] != 3 && name[4] != 6) return -EINVAL; /* NET_RT_IFLIST / NET_RT_IFLIST2 */
    return do_iflist(old, oldlen, name[3], name[5], name[4] == 6);
}
