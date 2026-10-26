#ifndef LINUX_OPENAT_H
#define LINUX_OPENAT_H

long sys_openat(int fd, const char* filename, int flags, unsigned int mode);
long sys_openat_nocancel(int fd, const char* filename, int flags, unsigned int mode);

long sys_openat_dprotected_np(int fd, const char *path, int flags, int protection_class, int dpflags, unsigned int mode, int authfd);

#endif // LINUX_OPENAT_H
