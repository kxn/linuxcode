#include "identifier-translation.h"
#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define CHECK(value) do { ++checks; if (!(value)) { fprintf(stderr, "OD_IDENTITY_FAIL line=%d check=%u\n", __LINE__, checks); return 1; } } while (0)

int main(void) {
    const unsigned char user_prefix[12] = {255,255,238,238,221,221,204,204,187,187,170,170};
    const unsigned char group_prefix[12] = {171,205,239,171,205,239,171,205,239,171,205,239};
    const id_t values[] = {0,282,501,65534,0x10203040,0xffffffed};
    for (unsigned i = 0; i < sizeof(values)/sizeof(*values); ++i) {
        for (int group = 0; group <= 1; ++group) {
            int input_type = group ? ID_TYPE_GID : ID_TYPE_UID;
            int expected_kind = group ? MBR_REC_TYPE_GROUP : MBR_REC_TYPE_USER;
            void *result = NULL;
            size_t length = 0;
            int kind = 0;
            CHECK(od_identifier_resolve(input_type, &values[i], sizeof(id_t), ID_TYPE_UUID, &result, &length, &kind) == 0);
            uint32_t network = htonl(values[i]);
            CHECK(length == 16 && kind == expected_kind);
            CHECK(!memcmp(result, group ? group_prefix : user_prefix, 12));
            CHECK(!memcmp((char *)result + 12, &network, 4));
            id_t decoded = 0;
            int decoded_kind = 0;
            CHECK(od_compat_uuid_decode(result, &decoded, &decoded_kind) == 0);
            CHECK(decoded == values[i] && decoded_kind == expected_kind);
            void *reverse = NULL;
            size_t reverse_length = 0;
            CHECK(od_identifier_resolve(ID_TYPE_UUID, result, length, ID_TYPE_UID_OR_GID,
                                        &reverse, &reverse_length, &decoded_kind) == 0);
            CHECK(reverse_length == sizeof(id_t) && *(id_t *)reverse == values[i] && decoded_kind == expected_kind);
            free(reverse);
            free(result);
        }
    }
    for (int group = 0; group <= 1; ++group) {
        id_t root = 0;
        void *name = NULL;
        size_t size = 0;
        int kind = 0;
        CHECK(od_identifier_resolve(group ? ID_TYPE_GID : ID_TYPE_UID, &root, sizeof(root), ID_TYPE_NAME, &name, &size, &kind) == 0);
        CHECK(size > 1 && ((char *)name)[size - 1] == 0);
        void *identifier = NULL;
        size_t identifier_size = 0;
        CHECK(od_identifier_resolve(group ? ID_TYPE_GROUPNAME : ID_TYPE_USERNAME, name, size - 1,
                                    ID_TYPE_UUID, &identifier, &identifier_size, &kind) == 0);
        uint32_t zero = 0;
        CHECK(identifier_size == 16 && !memcmp(identifier, group ? group_prefix : user_prefix, 12) &&
              !memcmp((char *)identifier + 12, &zero, 4));
        free(identifier);
        CHECK(od_identifier_resolve(group ? ID_TYPE_GROUPNAME : ID_TYPE_USERNAME, name, size,
                                    group ? ID_TYPE_GID : ID_TYPE_UID, &identifier, &identifier_size, &kind) == 0);
        CHECK(identifier_size == sizeof(id_t) && *(id_t *)identifier == 0);
        free(identifier); free(name);
    }
    id_t id = 282;
    void *output = (void *)(uintptr_t)0x1357;
    size_t output_size = 0x2468;
    int kind = 0x3456;
#define ERROR_CALL(type, value, length, target, error) do { \
    CHECK(od_identifier_resolve(type, value, length, target, &output, &output_size, &kind) == error); \
    CHECK(output == (void *)(uintptr_t)0x1357 && output_size == 0x2468 && kind == 0x3456); \
} while (0)
    ERROR_CALL(ID_TYPE_UID, &id, 3, ID_TYPE_UUID, EINVAL);
    ERROR_CALL(ID_TYPE_GID, &id, 0, ID_TYPE_UUID, EINVAL);
    ERROR_CALL(ID_TYPE_UID, NULL, sizeof(id), ID_TYPE_UUID, EINVAL);
    ERROR_CALL(ID_TYPE_GID, &id, sizeof(id), ID_TYPE_UID, EINVAL);
    const char embedded[] = {'r','o','o','t',0,'x'};
    ERROR_CALL(ID_TYPE_USERNAME, embedded, sizeof(embedded), ID_TYPE_UUID, EINVAL);
    ERROR_CALL(ID_TYPE_USERNAME, "", 1, ID_TYPE_UUID, EINVAL);
    ERROR_CALL(ID_TYPE_USERNAME, "x", 1024 * 1024 + 1, ID_TYPE_UUID, EINVAL);
    ERROR_CALL(9876, &id, sizeof(id), ID_TYPE_UUID, ENOSYS);
    ERROR_CALL(ID_TYPE_UID, &id, sizeof(id), 9876, ENOSYS);
    const uuid_t unknown = {0x55};
    ERROR_CALL(ID_TYPE_UUID, unknown, sizeof(unknown), ID_TYPE_UID_OR_GID, ENOENT);
    ERROR_CALL(ID_TYPE_UUID, unknown, 15, ID_TYPE_UID_OR_GID, EINVAL);
    const char missing[] = "linuxcode-test-record-does-not-exist-771985307";
    ERROR_CALL(ID_TYPE_USERNAME, missing, strlen(missing), ID_TYPE_UUID, ENOENT);
    ERROR_CALL(ID_TYPE_GROUPNAME, missing, strlen(missing), ID_TYPE_UUID, ENOENT);
    printf("OD_IDENTIFIER_COMPLETE_HOST_OK checks=%u\n", checks);
    return 0;
}
