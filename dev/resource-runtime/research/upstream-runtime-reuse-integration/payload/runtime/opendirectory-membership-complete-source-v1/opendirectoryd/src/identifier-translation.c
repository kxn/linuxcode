/*
 * Local passwd/group identifier backend for Darling OpenDirectory.
 * Compatibility prefixes and encoding/decoding derive from Apple's Libinfo
 * membership.subproj/membership.c (Copyright 2004-2018 Apple Inc., APSL 1.1).
 * No generated UUID database or authorization result is fabricated here.
 */
#include "identifier-translation.h"
#include <arpa/inet.h>
#include <errno.h>
#include <grp.h>
#include <pwd.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static const uuid_t user_prefix = {0xff,0xff,0xee,0xee,0xdd,0xdd,0xcc,0xcc,0xbb,0xbb,0xaa,0xaa,0,0,0,0};
static const uuid_t group_prefix = {0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0xab,0xcd,0xef,0,0,0,0};
_Static_assert(sizeof(id_t) == 4, "Darwin identity wire IDs have 32 bits");

int od_compat_uuid_decode(const uuid_t uuid, id_t *identifier, int *record_type) {
    if (!uuid || !identifier || !record_type) return EINVAL;
    int kind;
    if (!memcmp(uuid, user_prefix, 12)) kind = MBR_REC_TYPE_USER;
    else if (!memcmp(uuid, group_prefix, 12)) kind = MBR_REC_TYPE_GROUP;
    else return ENOENT;
    uint32_t network;
    memcpy(&network, uuid + 12, sizeof(network));
    *identifier = ntohl(network);
    *record_type = kind;
    return 0;
}

static void encode(id_t identifier, int kind, uuid_t result) {
    memcpy(result, kind == MBR_REC_TYPE_USER ? user_prefix : group_prefix, 12);
    uint32_t network = htonl(identifier);
    memcpy(result + 12, &network, sizeof(network));
}

static int lookup(int kind, const char *name, id_t requested, id_t *actual, char **canonical) {
    size_t size = 4096;
    char *buffer = NULL;
    int status;
    for (;;) {
        char *next = realloc(buffer, size);
        if (!next) { free(buffer); return ENOMEM; }
        buffer = next;
        const char *found_name = NULL;
        id_t found_id = 0;
        if (kind == MBR_REC_TYPE_USER) {
            struct passwd record, *found = NULL;
            status = name ? getpwnam_r(name, &record, buffer, size, &found) :
                            getpwuid_r(requested, &record, buffer, size, &found);
            if (!status && found) { found_name = record.pw_name; found_id = record.pw_uid; }
        } else {
            struct group record, *found = NULL;
            status = name ? getgrnam_r(name, &record, buffer, size, &found) :
                            getgrgid_r(requested, &record, buffer, size, &found);
            if (!status && found) { found_name = record.gr_name; found_id = record.gr_gid; }
        }
        if (status == ERANGE) {
            if (size > SIZE_MAX / 2) { free(buffer); return ENOMEM; }
            size *= 2;
            continue;
        }
        if (!status && !found_name) status = ENOENT;
        char *copy = NULL;
        if (!status && canonical) {
            copy = strdup(found_name);
            if (!copy) status = ENOMEM;
        }
        if (!status) {
            *actual = found_id;
            if (canonical) *canonical = copy;
        }
        free(buffer);
        return status;
    }
}

int od_identifier_resolve(int type, const void *identifier, size_t size,
                         int target, void **result, size_t *result_size, int *record_type) {
    if (!identifier || !result || !result_size || !record_type || !size) return EINVAL;
    id_t id = 0;
    int kind = 0, status = 0;
    char *name = NULL;
    if (type == ID_TYPE_UID || type == ID_TYPE_GID) {
        if (size != sizeof(id)) return EINVAL;
        memcpy(&id, identifier, sizeof(id));
        kind = type == ID_TYPE_UID ? MBR_REC_TYPE_USER : MBR_REC_TYPE_GROUP;
    } else if (type == ID_TYPE_UUID) {
        if (size != sizeof(uuid_t)) return EINVAL;
        status = od_compat_uuid_decode(identifier, &id, &kind);
        if (status) return status;
    } else if (type == ID_TYPE_USERNAME || type == ID_TYPE_GROUPNAME) {
        if (size > 1024 * 1024) return EINVAL;
        const char *nul = memchr(identifier, 0, size);
        if (nul && nul != (const char *)identifier + size - 1) return EINVAL;
        size_t length = nul ? size - 1 : size;
        if (!length) return EINVAL;
        char *input = malloc(length + 1);
        if (!input) return ENOMEM;
        memcpy(input, identifier, length); input[length] = 0;
        kind = type == ID_TYPE_USERNAME ? MBR_REC_TYPE_USER : MBR_REC_TYPE_GROUP;
        status = lookup(kind, input, 0, &id, &name);
        free(input);
        if (status) return status;
    } else return ENOSYS;

    void *data = NULL;
    size_t output_size;
    if (target == ID_TYPE_UUID) {
        output_size = sizeof(uuid_t);
        data = malloc(output_size);
        if (data) encode(id, kind, data);
    } else if (target == ID_TYPE_UID_OR_GID || target == ID_TYPE_UID || target == ID_TYPE_GID) {
        if ((target == ID_TYPE_UID && kind != MBR_REC_TYPE_USER) ||
            (target == ID_TYPE_GID && kind != MBR_REC_TYPE_GROUP)) { free(name); return EINVAL; }
        output_size = sizeof(id);
        data = malloc(output_size);
        if (data) memcpy(data, &id, output_size);
    } else if (target == ID_TYPE_USERNAME || target == ID_TYPE_GROUPNAME || target == ID_TYPE_NAME) {
        if ((target == ID_TYPE_USERNAME && kind != MBR_REC_TYPE_USER) ||
            (target == ID_TYPE_GROUPNAME && kind != MBR_REC_TYPE_GROUP)) { free(name); return EINVAL; }
        if (!name) status = lookup(kind, NULL, id, &id, &name);
        if (status) return status;
        output_size = strlen(name) + 1;
        data = name; name = NULL;
    } else { free(name); return ENOSYS; }
    free(name);
    if (!data) return ENOMEM;
    *result = data;
    *result_size = output_size;
    *record_type = kind;
    return 0;
}
