#include <IOKit/IOKitLib.h>
#include <IOKit/pwr_mgt/IOPMLib.h>
#include <mach/mach.h>
#include <stdio.h>

/* Passive registration only: no host sleep request or fabricated callback. */
static void power(void *context, io_service_t service, natural_t message, void *argument) {
    (void)context; (void)service; (void)message; (void)argument;
}

int main(void) {
    setbuf(stdout, NULL);
    int failed = 0;
    mach_port_t master = 0;
    kern_return_t status = IOMainPort(MACH_PORT_NULL, &master);
    printf("IOPOWER_STAGE main-port status=%u present=%d\n", status, master != 0);
    if (status || !master) failed = 1;

    io_registry_entry_t root = IORegistryEntryFromPath(master, "IOPower:/IOPowerConnection/IOPMrootDomain");
    printf("IOPOWER_STAGE root-domain present=%d\n", root != 0);
    if (!root) failed = 1;
    IONotificationPortRef notify = IONotificationPortCreate(master);
    mach_port_type_t type = 0;
    status = notify ? mach_port_type(mach_task_self(), IONotificationPortGetMachPort(notify), &type) : KERN_INVALID_ARGUMENT;
    printf("IOPOWER_STAGE notification-port status=%u present=%d receive-right=%d\n", status, notify != NULL, (type & MACH_PORT_TYPE_RECEIVE) != 0);
    if (status || !notify || !(type & MACH_PORT_TYPE_RECEIVE)) failed = 1;

    io_connect_t connection = 0;
    if (root) {
        status = IOServiceOpen(root, mach_task_self(), 0, &connection);
        printf("IOPOWER_STAGE direct-open status=%u present=%d\n", status, connection != 0);
        if (status || !connection) failed = 1;
    }
    io_object_t interest = 0;
    if (root && notify) {
        status = IOServiceAddInterestNotification(notify, root, kIOAppPowerStateInterest, power, NULL, &interest);
        printf("IOPOWER_STAGE direct-interest status=%u present=%d\n", status, interest != 0);
        if (status || !interest) failed = 1;
    }
    if (interest) {
        status = IODeregisterForSystemPower(&interest);
        printf("IOPOWER_STAGE direct-deregister status=%u cleared=%d\n", status, interest == 0);
        if (status || interest) failed = 1;
    }
    if (connection) {
        status = IOServiceClose(connection);
        printf("IOPOWER_STAGE direct-close status=%u\n", status);
        if (status) failed = 1;
    }
    if (notify) IONotificationPortDestroy(notify);

    notify = NULL; interest = 0;
    connection = IORegisterForSystemPower(NULL, &notify, power, &interest);
    printf("IOPOWER_STAGE convenience connection=%d notification-port=%d notifier=%d\n", connection != 0, notify != NULL, interest != 0);
    if (!connection || !notify || !interest) failed = 1;
    if (interest) {
        status = IODeregisterForSystemPower(&interest);
        printf("IOPOWER_STAGE convenience-deregister status=%u cleared=%d\n", status, interest == 0);
        if (status || interest) failed = 1;
    }
    if (connection) {
        status = IOServiceClose(connection);
        printf("IOPOWER_STAGE convenience-close status=%u\n", status);
        if (status) failed = 1;
    }
    if (notify) IONotificationPortDestroy(notify);
    if (root) IOObjectRelease(root);
    if (master) mach_port_deallocate(mach_task_self(), master);
    printf("IOPOWER_REGISTRATION_SMOKE_STATUS %d\n", failed);
    return failed;
}
