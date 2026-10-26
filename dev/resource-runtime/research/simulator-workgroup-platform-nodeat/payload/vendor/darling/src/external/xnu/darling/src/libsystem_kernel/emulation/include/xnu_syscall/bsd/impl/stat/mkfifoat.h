#ifndef _DARLING_MKFIFOAT_H
#define _DARLING_MKFIFOAT_H
long sys_mkfifoat(int fd, const char *path, unsigned int mode);
long sys_mknodat(int fd, const char *path, unsigned int mode, unsigned int device);
#endif
