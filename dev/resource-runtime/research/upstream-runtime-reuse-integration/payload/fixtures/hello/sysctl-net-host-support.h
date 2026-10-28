#ifndef LINUXCODE_SYSCTL_NET_HOST_SUPPORT_H
#define LINUXCODE_SYSCTL_NET_HOST_SUPPORT_H
struct host_interface_snapshot {
    unsigned int index, flags, hardware_type, mtu, address_length;
    unsigned char address[24];
    unsigned long long rx_bytes, tx_bytes, rx_packets, tx_packets;
};
int host_interface_snapshot(const char*, struct host_interface_snapshot*);
unsigned int host_interface_count(void);
int host_route_present(unsigned int,unsigned int,const unsigned char*,const unsigned char*,const unsigned char*);
#endif
