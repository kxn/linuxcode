#ifndef DARLING_KERNEL_QUARANTINE_H
#define DARLING_KERNEL_QUARANTINE_H
#include <stdint.h>
int quarantine_kernel_ready(void);
int quarantine_process_active(void);
void quarantine_created_fd(int fd);
void quarantine_changed_fd(int fd,int operation);
void quarantine_changed_path(int dfd,const char *linux_path,int nofollow,int operation);
void quarantine_created_path(int dfd,const char *linux_path,int nofollow);
int quarantine_check_exec_fd(int fd);
int quarantine_xattr_name(const char *name,const char **translated,int writing);
int darwin_xattr_name(const char *name,const char **translated,int writing,char storage[256]);
long darwin_xattr_list(const char *path,int fd,int nofollow,char *output,unsigned long size);
void quarantine_removed_fd(int fd,const char *logical_name);
void quarantine_removed_path(int dfd,const char *path,int nofollow,const char *logical_name);
#endif
