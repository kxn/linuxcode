#include <darling/emulation/xnu_syscall/bsd/helper/network/duct.h>

#include <sys/socket.h>
#include <sys/errno.h>

#include <darling/emulation/conversion/network/duct.h>
#include <darling/emulation/conversion/errno.h>
#include <darling/emulation/linux_premigration/vchroot_expand.h>
#include <darling/emulation/common/bsdthread/per_thread_wd.h>

unsigned long sockaddr_fixup_size_from_bsd(const void* bsd_sockaddr, int bsd_sockaddr_len) {
    // The converter rejects invalid lengths before inspecting the address.
    // Keep allocation bounded even when a caller passes a negative socklen.
    if (bsd_sockaddr_len < 2 || bsd_sockaddr_len > 512)
        return sizeof(struct sockaddr_fixup);
	return (((const struct sockaddr_fixup*)bsd_sockaddr)->bsd_family == PF_LOCAL) ? sizeof(struct sockaddr_fixup) : bsd_sockaddr_len;
}

int sockaddr_fixup_from_bsd(struct sockaddr_fixup* out, const void* bsd_sockaddr, int bsd_sockaddr_len) {
	int ret = bsd_sockaddr_len;
    if (bsd_sockaddr_len < 2 || bsd_sockaddr_len > 512)
        return -EINVAL;
    const struct sockaddr_fixup* input = bsd_sockaddr;
    if (input->bsd_family == PF_LOCAL && bsd_sockaddr_len > sizeof(*out))
        return -EINVAL;

	memcpy(out, bsd_sockaddr, bsd_sockaddr_len);

	out->linux_family = sfamily_bsd_to_linux(out->bsd_family);

	if (out->linux_family == LINUX_PF_LOCAL) {
		struct vchroot_expand_args vc;
		vc.flags = VCHROOT_FOLLOW;
		vc.dfd = get_perthread_wd();

        // Darwin AF_UNIX addresses may end exactly at socklen, without a NUL.
        // Do not let strcpy consume unrelated bytes in the caller's stack.
        const unsigned path_bytes = bsd_sockaddr_len - __builtin_offsetof(struct sockaddr_fixup, sun_path);
        memcpy(vc.path, out->sun_path, path_bytes);
        vc.path[path_bytes] = '\0';

		ret = vchroot_expand(&vc);
		if (ret < 0)
			return errno_linux_to_bsd(ret);

        const unsigned expanded_bytes = strlen(vc.path);
        if (expanded_bytes > sizeof(out->sun_path))
            return -ENAMETOOLONG;
        memcpy(out->sun_path, vc.path, expanded_bytes);
        if (expanded_bytes < sizeof(out->sun_path))
            out->sun_path[expanded_bytes] = '\0';
        ret = __builtin_offsetof(struct sockaddr_fixup, sun_path) + expanded_bytes;
	}

	return ret;
}

int sockaddr_fixup_from_linux(struct sockaddr_fixup* out, const void* linux_sockaddr, int linux_sockaddr_len) {
	int ret = linux_sockaddr_len;

	memcpy(out, linux_sockaddr, linux_sockaddr_len);

	out->bsd_family = sfamily_linux_to_bsd(out->linux_family);

	if (out->bsd_family == PF_LOCAL) {
		struct vchroot_unexpand_args vc;
		strcpy(vc.path, out->sun_path);

		ret = vchroot_unexpand(&vc);
		if (ret < 0)
			return errno_linux_to_bsd(ret);

		strncpy(out->sun_path, vc.path, sizeof(out->sun_path) - 1);
		out->sun_path[sizeof(out->sun_path) - 1] = '\0';
		ret = sizeof(*out) - sizeof(out->sun_path) + strlen(out->sun_path) + 1;
	}

	if (ret >= 0) {
		out->bsd_length = ret;
	}

	return ret;
}
