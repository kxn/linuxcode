#include <assert.h>
#include <resolv.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>

extern int __res_vinit(res_state, int);

int main(void) {
    setbuf(stdout, NULL);
    struct __res_state state;
    memset(&state, 0, sizeof(state));
    assert(res_ninit(&state) == 0);
    assert(state.nscount > 0 && !(state.options & RES_USEVC));
    puts("RESOLVER_OPTIONS_CONFIGURED_DEFAULT_UDP_OK");
    state.options |= RES_USEVC;
    assert(__res_vinit(&state, 1) == 0);
    assert(state.nscount > 0 && (state.options & RES_USEVC));
    puts("RESOLVER_OPTIONS_CALLER_TCP_FLAG_PRESERVED_OK");
    assert(res_ninit(&state) == 0);
    assert(state.nscount > 0 && !(state.options & RES_USEVC));
    union res_sockaddr_union input[2], output[2];
    memset(input, 0, sizeof(input)); memset(output, 0, sizeof(output));
    for (int i = 0; i < 2; ++i) {
        input[i].sin.sin_family = AF_INET;
        input[i].sin.sin_len = sizeof(struct sockaddr_in);
        input[i].sin.sin_port = htons(53 + i);
        assert(inet_pton(AF_INET, i ? "192.0.2.2" : "192.0.2.1", &input[i].sin.sin_addr) == 1);
    }
    res_setservers(&state, input, 1); assert(state.nscount == 1);
    assert(res_getservers(&state, output, 2) == 1);
    assert(output[0].sin.sin_port == input[0].sin.sin_port);
    assert(output[0].sin.sin_addr.s_addr == input[0].sin.sin_addr.s_addr);
    state.options |= RES_USEVC;
    res_setservers(&state, input, 2); assert(state.nscount == 2 && (state.options & RES_USEVC));
    assert(res_getservers(&state, output, 2) == 2);
    for (int i = 0; i < 2; ++i) {
        assert(output[i].sin.sin_port == input[i].sin.sin_port);
        assert(output[i].sin.sin_addr.s_addr == input[i].sin.sin_addr.s_addr);
    }
    res_ndestroy(&state);
    puts("PRIVATE_NATIVE_RESOLVER_OPTIONS_DEFAULT_UDP_AND_EXPLICIT_TCP_FLAGS_OK");
    return 0;
}
