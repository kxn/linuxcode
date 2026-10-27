#include <assert.h>
#include <netdb.h>
#include <errno.h>
#include <resolv.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    assert(argc == 2);
    setbuf(stdout, NULL);
    alarm(30);
    FILE *actual = fopen("/etc/resolv.conf", "rb");
    FILE *expected = fopen(argv[1], "rb");
    assert(actual && expected);
    for (;;) {
        int a = fgetc(actual), b = fgetc(expected);
        assert(a == b);
        if (a == EOF) break;
    }
    fclose(actual); fclose(expected);
    puts("PRIVATE_NATIVE_RESOLVER_EXACT_CONFIG_OK");
    const char *hosts[] = {"api.nuget.org", "nuget.azure.cn"};
    for (unsigned i = 0; i < 2; ++i) {
        unsigned char response[4096];
        int length = res_query(hosts[i], 1, 1, response, sizeof(response));
        printf("PRIVATE_NATIVE_RAW_DNS %s length=%d errno=%d h_errno=%d flags=%04x answers=%u\n",
               hosts[i], length, errno, h_errno,
               length >= 12 ? (response[2] << 8) | response[3] : 0,
               length >= 12 ? (response[6] << 8) | response[7] : 0);
        struct hostent *host = gethostbyname(hosts[i]);
        printf("PRIVATE_NATIVE_HOSTENT %s found=%d h_errno=%d\n", hosts[i], host != NULL, h_errno);
        struct addrinfo hints = {0}, *addresses = NULL;
        hints.ai_socktype = SOCK_STREAM;
        int status = getaddrinfo(hosts[i], "443", &hints, &addresses);
        printf("PRIVATE_NATIVE_DNS %s status=%d\n", hosts[i], status);
        if (status || !addresses) return 1;
        unsigned count = 0;
        for (struct addrinfo *p = addresses; p; p = p->ai_next) ++count;
        assert(count > 0);
        freeaddrinfo(addresses);
    }
    puts("PRIVATE_NATIVE_RESOLVER_REAL_LOOKUPS_OK");
    return 0;
}
