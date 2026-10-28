#include <membership.h>
#include <uuid/uuid.h>
#include <pwd.h>
#include <grp.h>
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(value) do { ++checks; if (!(value)) { printf("MEMBERSHIP_FAILED line=%d check=%u\n", __LINE__, checks); return 1; } } while (0)
typedef int (*translate_fn)(int, const void *, size_t, int, void **, int *);
typedef int (*name_uuid_fn)(const char *, uuid_t);
static const unsigned char user_prefix[12] = {255,255,238,238,221,221,204,204,187,187,170,170};
static const unsigned char group_prefix[12] = {171,205,239,171,205,239,171,205,239,171,205,239};

int main(void) {
    setbuf(stdout, NULL);
    translate_fn translate = dlsym(RTLD_DEFAULT, "mbr_identifier_translate");
    name_uuid_fn username = dlsym(RTLD_DEFAULT, "mbr_user_name_to_uuid");
    name_uuid_fn groupname = dlsym(RTLD_DEFAULT, "mbr_group_name_to_uuid");
    CHECK(translate && username && groupname);
    const uint32_t identifiers[] = {0, 282, 501, 65534, UINT32_C(0x10203040), UINT32_C(0xffffffed)};
    unsigned root_record = 0, trust_record = 0, missing_users = 0;
    for (unsigned i = 0; i < sizeof(identifiers)/sizeof(*identifiers); ++i) {
        uint32_t value = identifiers[i], network = htonl(value);
        uuid_t user, group, named;
        int status = mbr_uid_to_uuid(value, user);
        printf("MEMBERSHIP_UID index=%u status=%d\n", i, status);
        CHECK(status == 0);
        CHECK(mbr_gid_to_uuid(value, group) == 0);
        CHECK(uuid_compare(user, group) != 0);
        id_t recovered = 0;
        int type = -1;
        CHECK(mbr_uuid_to_id(user, &recovered, &type) == 0 && recovered == value && type == ID_TYPE_UID);
        CHECK(mbr_uuid_to_id(group, &recovered, &type) == 0 && recovered == value && type == ID_TYPE_GID);
        CHECK(!memcmp(group, group_prefix, 12) && !memcmp(group + 12, &network, 4));

        struct passwd record, *found = NULL;
        char buffer[65536];
        CHECK(getpwuid_r(value, &record, buffer, sizeof(buffer), &found) == 0);
        if (found) {
            CHECK(username(record.pw_name, named) == 0 && uuid_compare(user, named) == 0);
            if (value == 0) root_record = 1;
            if (value == 282) trust_record = 1;
        } else {
            ++missing_users;
            CHECK(!memcmp(user, user_prefix, 12) && !memcmp(user + 12, &network, 4));
        }
        if (!memcmp(user, user_prefix, 12)) CHECK(!memcmp(user + 12, &network, 4));
        puts("MEMBERSHIP_CASE_ROUNDTRIP_NAME_AND_TYPE_OK");
    }
    CHECK(root_record && trust_record && missing_users > 0);
    uint32_t value = 282;
    void *result = (void *)(uintptr_t)0x1357;
    int type = 0x2468;
    CHECK(translate(ID_TYPE_UID, &value, 3, ID_TYPE_UUID, &result, &type) == EINVAL);
    CHECK(result == (void *)(uintptr_t)0x1357 && type == 0x2468);
    CHECK(translate(ID_TYPE_GID, &value, 0, ID_TYPE_UUID, &result, &type) == EIO);
    CHECK(result == (void *)(uintptr_t)0x1357);
    uuid_t bogus = {0};
    CHECK(translate(ID_TYPE_UUID, bogus, 15, ID_TYPE_UID, &result, &type) == EINVAL);
    CHECK(result == (void *)(uintptr_t)0x1357 && type == 0x2468);
    CHECK(translate(ID_TYPE_UID, NULL, sizeof(value), ID_TYPE_UUID, &result, &type) == EIO);
    CHECK(result == (void *)(uintptr_t)0x1357);
    printf("MEMBERSHIP_IDENTITY_TRANSLATION_NATIVE_OK checks=%u real-root-and-trustd-records=1 missing-ID-is-not-existence-proof=1\n", checks);

    // Optional independent diagnostic of the existing daemon's authorization
    // behavior. Identity conversion success alone must not establish membership.
    if (getenv("LINUXCODE_MEMBERSHIP_CHECK_AUTH")) {
        uuid_t absent_user, absent_group;
        CHECK(mbr_uid_to_uuid(UINT32_C(0xffffffed), absent_user) == 0);
        CHECK(mbr_gid_to_uuid(UINT32_C(0xffffffec), absent_group) == 0);
        int member = -1;
        int status = mbr_check_membership(absent_user, absent_group, &member);
        printf("MEMBERSHIP_ABSENT_RECORDS_AUTHORIZATION status=%d member=%d\n", status, member);
        if (status == 0 && member) {
            puts("MEMBERSHIP_EXISTING_DAEMON_INCORRECTLY_ACCEPTED_ABSENT_RECORDS");
            return 2;
        }
        puts("MEMBERSHIP_ABSENT_RECORDS_NOT_AUTHORIZED_OK");
    }
    return 0;
}
