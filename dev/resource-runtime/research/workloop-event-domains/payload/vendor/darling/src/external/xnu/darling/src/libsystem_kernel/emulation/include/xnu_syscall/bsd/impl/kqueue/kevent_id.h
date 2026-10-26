#ifndef DARLING_KEVENT_ID_H
#define DARLING_KEVENT_ID_H
#include <stdint.h>
#define PRIVATE 1
#include <sys/event.h>
long sys_kevent_id(uint64_t id, const struct kevent_qos_s* changes, int nchanges,
        struct kevent_qos_s* events, int nevents, void* data, unsigned long* available, unsigned flags);
#endif
