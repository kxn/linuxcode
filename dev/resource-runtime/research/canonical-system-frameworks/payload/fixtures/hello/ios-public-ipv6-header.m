#import <netinet/in.h>
#ifdef DIRECT_PRIVATE_IPV6_IMPORT
#import <netinet6/in6.h>
#endif
_Static_assert(sizeof(struct sockaddr_in6)==28,"iOS IPv6 socket ABI");
_Static_assert(sizeof(struct in6_addr)==16,"IPv6 address ABI");
int has_link_local_address(const struct in6_addr *address) {
 return IN6_IS_ADDR_LINKLOCAL(address);
}
