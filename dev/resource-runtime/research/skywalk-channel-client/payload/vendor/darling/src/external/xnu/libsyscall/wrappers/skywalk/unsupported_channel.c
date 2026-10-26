#include <errno.h>
#include <string.h>
#include <strings.h>
#include <skywalk/os_skywalk_private.h>

/* Real user-space channel/attribute/ring logic is supplied by os_channel.c.
 * Linux has no Darwin Skywalk channel transport or shared schema mapping.
 * Fail creation and kernel operations explicitly instead of fabricating a
 * descriptor, ring mapping, completion or packet transfer. */
int __channel_open(struct ch_init *init, const uint32_t length)
{
    (void)init; (void)length; errno = ENOTSUP; return -1;
}
int __channel_get_info(int fd, struct ch_info *info, const uint32_t length)
{
    (void)fd; (void)info; (void)length; errno = ENOTSUP; return -1;
}
int __channel_sync(int fd, const int mode, const sync_flags_t flags)
{
    (void)fd; (void)mode; (void)flags; errno = ENOTSUP; return -1;
}
int __channel_set_opt(int fd, const uint32_t option, const void *value, const uint32_t length)
{
    (void)fd; (void)option; (void)value; (void)length; errno = ENOTSUP; return -1;
}
