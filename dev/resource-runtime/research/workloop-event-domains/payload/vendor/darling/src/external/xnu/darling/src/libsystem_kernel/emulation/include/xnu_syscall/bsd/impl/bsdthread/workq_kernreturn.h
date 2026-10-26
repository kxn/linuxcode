#ifndef WORKQ_KERNRETURN_H
#define WORKQ_KERNRETURN_H

#define PRIVATE 1
#include <sys/event.h>
#include <stdint.h>
#include <stdbool.h>

// Darling specific
#define WQOPS_QUEUE_REQTHREAD_FOR_KEVENT  0x100020
#define WQOPS_QUEUE_REQTHREAD_FOR_WORKLOOP 0x100021
#define WQOPS_REGISTER_WORKLOOP_CALLBACK  0x100022

struct wq_kevent_data
{
	struct kevent_qos_s* events;
	int nevents;
	int capacity;
	int sem;
	uint64_t workloop_id;
};

struct timespec;

long sys_workq_kernreturn(int options, void* item, int affinity, int prio);

bool workq_workloop_callback_registered(void);
uint64_t workq_current_workloop_id(void);

int sem_down(int* sem, int timeout);
void sem_up(int* sem);

#endif // WORKQ_KERNRETURN_H
