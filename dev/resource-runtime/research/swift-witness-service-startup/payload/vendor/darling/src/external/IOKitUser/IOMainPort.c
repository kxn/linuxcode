#include <IOKit/IOKitLib.h>

/* The native Intel implementation forwards directly to IOMasterPort. */
kern_return_t
IOMainPort(mach_port_t bootstrapPort, mach_port_t *mainPort)
{
    return IOMasterPort(bootstrapPort, mainPort);
}
