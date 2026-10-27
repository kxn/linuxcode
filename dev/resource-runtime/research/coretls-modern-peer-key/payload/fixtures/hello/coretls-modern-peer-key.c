#include "tls_handshake_priv.h"
#include "sslCrypto.h"
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static tls_buffer load(const char *path) {
    FILE *file = fopen(path, "rb"); assert(file);
    assert(fseek(file, 0, SEEK_END) == 0);
    long size = ftell(file); assert(size > 0);
    rewind(file);
    tls_buffer result = { .length = size, .data = malloc(size) };
    assert(result.data && fread(result.data, 1, size, file) == (size_t)size);
    fclose(file); return result;
}

int main(int argc, char **argv) {
    assert(argc == 7); setbuf(stdout, NULL); alarm(35);
    void *library = dlopen(argv[1], RTLD_LAZY | RTLD_LOCAL);
    if (!library) fprintf(stderr, "HELPER_LOAD_ERROR %s\n", dlerror());
    assert(library);
    int (*set_key)(tls_handshake_t) = dlsym(library, "tls_helper_set_peer_pubkey");
    assert(set_key);
    tls_buffer digest = load(argv[2]); assert(digest.length == 32);
    for (int i = 0; i < 2; ++i) {
        tls_handshake_t context = tls_handshake_create(false, false); assert(context);
        context->peerCert = calloc(1, sizeof(*context->peerCert)); assert(context->peerCert);
        context->peerCert->derCert = load(argv[3 + i * 2]);
        tls_buffer signature = load(argv[4 + i * 2]);
        tls_handshake_trust_t before = context->peerTrust;
        int status = set_key(context);
        printf("CORETLS_MODERN_KEY type=%s status=%d\n", i == 0 ? "RSA" : "P256", status);
        assert(status == 0 && context->peerPubKey.isRSA == (i == 0));
        assert(context->peerTrust == before);
        int valid = i == 0 ? sslRsaVerify(&context->peerPubKey, tls_hash_algorithm_SHA256,
            digest.data, digest.length, signature.data, signature.length) :
            sslRawVerify(&context->peerPubKey, digest.data, digest.length, signature.data, signature.length);
        assert(valid == 0);
        digest.data[0] ^= 1;
        int invalid = i == 0 ? sslRsaVerify(&context->peerPubKey, tls_hash_algorithm_SHA256,
            digest.data, digest.length, signature.data, signature.length) :
            sslRawVerify(&context->peerPubKey, digest.data, digest.length, signature.data, signature.length);
        digest.data[0] ^= 1; assert(invalid != 0);
        free(signature.data); tls_handshake_destroy(context);
    }
    tls_handshake_t empty = tls_handshake_create(false, false); assert(empty);
    assert(set_key(empty) == 0);
    empty->peerCert = calloc(1, sizeof(*empty->peerCert)); assert(empty->peerCert);
    empty->peerCert->derCert.length = 3;
    empty->peerCert->derCert.data = malloc(3); assert(empty->peerCert->derCert.data);
    memcpy(empty->peerCert->derCert.data, "bad", 3);
    assert(set_key(empty) != 0);
    tls_handshake_destroy(empty); free(digest.data); dlclose(library);
    puts("CORETLS_MODERN_PEER_KEYS_REAL_RSA_ECDSA_SIGNATURES_AND_MALFORMED_REJECTION_OK");
    return 0;
}
