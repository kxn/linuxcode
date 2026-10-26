// Linux-backed IOPower registry, Mach user clients, and resume notifications.
// Suspend permission barriers and power-control selectors are not implemented;
// unsupported operations must not report success.
#include "IOPowerRootDomain.h"
#import <Foundation/NSString.h>
#import <Foundation/NSNumber.h>
#include "IOUserClient.h"
#include "ServiceUserConnection.h"
#include "LinuxResumeClock.h"
#include "iokitd.h"
#include <IOKit/IOMessage.h>
#include <IOKit/OSMessageNotification.h>
#include <IOKit/pwr_mgt/IOPM.h>
#include <mach/mach.h>
#include <os/log.h>
#include <set>
#include <cstring>
#include <climits>
extern "C" {
#include "iokitmigServer.h"
int __linux_syscall(int number, ...);
}

namespace {
class PowerConnection : public IOUserClient {
public:
    explicit PowerConnection(IOPowerRootDomain* domain) : domain(domain) {}
    const char* className() const override { return "IOPMrootDomainUserClient"; }
    NSDictionary* matchingDictionary() override { return @{}; }
    IOExternalMethod* getExternalMethodForIndex(UInt32) override { return nullptr; }
    IOPowerRootDomain* domain;
    bool closed = false;
};

class PowerInterest : public IOObject {
public:
    PowerInterest(IOPowerRootDomain* domain, mach_port_t wake, const uint64_t* refs, unsigned count)
        : domain(domain), wake(wake) {
        std::memcpy(reference, refs, count * sizeof(*refs));
        interests.insert(this);
    }
    ~PowerInterest() override {
        interests.erase(this);
        mach_port_deallocate(mach_task_self(), wake);
    }
    const char* className() const override { return "IOServiceMessageUserNotification"; }
    void send(uint32_t message) {
        // Native IOKit consumes one service descriptor and a notifier send right.
        // These rights also let it suppress queued callbacks after deregistration.
#pragma pack(push, 4)
        struct Packet {
            mach_msg_header_t head;
            mach_msg_body_t body;
            mach_msg_port_descriptor_t service;
            OSNotificationHeader64 notification;
            IOServiceInterestContent64 content;
        } packet = {};
#pragma pack(pop)
        static_assert(sizeof(Packet) == 124, "Intel IOKit notification ABI");
        packet.head.msgh_bits = MACH_MSGH_BITS_COMPLEX |
            MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND, MACH_MSG_TYPE_MAKE_SEND);
        packet.head.msgh_size = sizeof(packet);
        packet.head.msgh_remote_port = wake;
        packet.head.msgh_local_port = port();
        packet.head.msgh_id = kOSNotificationMessageID;
        packet.body.msgh_descriptor_count = 1;
        packet.service.name = domain->port();
        packet.service.disposition = MACH_MSG_TYPE_MAKE_SEND;
        packet.service.type = MACH_MSG_PORT_DESCRIPTOR;
        packet.notification.type = kIOServiceMessageNotificationType;
        packet.notification.size = sizeof(packet.content);
        std::memcpy(packet.notification.reference, reference, sizeof(reference));
        packet.content.messageType = message;
        // Resume messages carry no acknowledgement token.
        kern_return_t kr = mach_msg(&packet.head, MACH_SEND_MSG | MACH_SEND_TIMEOUT,
            sizeof(packet), 0, MACH_PORT_NULL, 0, MACH_PORT_NULL);
        if (kr != KERN_SUCCESS)
            os_log_error(OS_LOG_DEFAULT, "IOPower resume notification delivery failed: %d", kr);
    }
    static std::set<PowerInterest*> interests;
private:
    IOPowerRootDomain* domain;
    mach_port_t wake;
    uint64_t reference[kOSAsyncRef64Count] = {};
};
std::set<PowerInterest*> PowerInterest::interests;

bool readLinuxClock(int which, int64_t& nanos) {
    // Linux x86_64 timespec, not the Darwin clock_gettime ABI.
    struct { int64_t sec, nsec; } value = {};
    if (__linux_syscall(228, which, &value) != 0 || value.sec < 0 ||
        value.nsec < 0 || value.nsec >= 1000000000 ||
        value.sec > (INT64_MAX - value.nsec) / 1000000000) return false;
    nanos = value.sec * 1000000000 + value.nsec;
    return true;
}
bool sample(LinuxResumeClock& clock, bool& resumed) {
    int64_t before, boot, after;
    if (!readLinuxClock(1, before) || !readLinuxClock(7, boot) || !readLinuxClock(1, after)) return false;
    resumed = clock.observe(before, boot, after);
    return true;
}
}

NSDictionary* IOPowerRootDomain::matchingDictionary() {
    return @{ @"IOProviderClass": @"IOPMrootDomain", @"IOClass": @"IOPMrootDomain" };
}
NSDictionary* IOPowerRootDomain::getProperties() {
    return @{ @"IOClass": @"IOPMrootDomain", @"DarlingPowerBackend": @"Linux CLOCK_BOOTTIME/CLOCK_MONOTONIC",
        @"DarlingPowerObservesResume": @YES, @"DarlingPowerSupportsSleepBarrier": @NO };
}
void IOPowerRootDomain::registerSelf(ServiceRegistry* registry) {
    static LinuxResumeClock clock;
    bool resumed;
    if (!sample(clock, resumed)) {
        os_log_error(OS_LOG_DEFAULT, "Linux suspend-aware clocks unavailable; IOPower domain not registered");
        return;
    }
    auto* connection = new IORegistryEntry;
    connection->registerInPlane(kIOPowerPlane, "IOPowerConnection", IORegistryEntry::root());
    auto* domain = new IOPowerRootDomain;
    domain->registerInPlane(kIOPowerPlane, "IOPMrootDomain", connection);
    domain->registerInPlane(kIOServicePlane, "IOPMrootDomain", IORegistryEntry::root());
    registry->registerService(domain);
    auto timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
    dispatch_source_set_timer(timer, dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), NSEC_PER_SEC, NSEC_PER_MSEC * 20);
    dispatch_source_set_event_handler(timer, ^{
        bool resumed;
        if (sample(clock, resumed) && resumed) {
            for (auto* interest : PowerInterest::interests) interest->send(kIOMessageSystemWillPowerOn);
            for (auto* interest : PowerInterest::interests) interest->send(kIOMessageSystemHasPoweredOn);
        }
    });
    dispatch_resume(timer);
}

kern_return_t is_io_service_open_extended(mach_port_t service, task_t owningTask, uint32_t type,
    NDR_record_t, io_buf_ptr_t properties, mach_msg_type_number_t propertiesCount,
    kern_return_t* result, mach_port_t* connection) {
    *connection = MACH_PORT_NULL;
    *result = kIOReturnUnsupported;
    auto* object = IOObject::lookup(service);
    auto* domain = dynamic_cast<IOPowerRootDomain*>(object);
    auto* userService = dynamic_cast<IOUserClient*>(object);
    pid_t owner = -1;
    if (!domain && !userService) *result = kIOReturnUnsupported;
    else if (type != 0 || propertiesCount) *result = kIOReturnUnsupported;
    else if (pid_for_task(owningTask, &owner) != KERN_SUCCESS || owner <= 0 || owner != g_iokitCurrentCallerPID)
        *result = kIOReturnNotPermitted;
    else {
        IOUserClient* client = domain ? static_cast<IOUserClient*>(new PowerConnection(domain)) :
            static_cast<IOUserClient*>(new ServiceUserConnection(userService, owner));
        *connection = client->port();
        client->releaseLater();
        *result = kIOReturnSuccess;
    }
    // MIG transfers both the task send right and any OOL properties to us.
    if (MACH_PORT_VALID(owningTask)) mach_port_deallocate(mach_task_self(), owningTask);
    if (properties && propertiesCount) vm_deallocate(mach_task_self(), (vm_address_t)properties, propertiesCount);
    return KERN_SUCCESS;
}
kern_return_t is_io_service_close(mach_port_t connection) {
    if (auto* generic = dynamic_cast<ServiceUserConnection*>(IOObject::lookup(connection))) return generic->close();
    auto* client = dynamic_cast<PowerConnection*>(IOObject::lookup(connection));
    if (!client || client->closed) return kIOReturnNotOpen;
    client->closed = true;
    return kIOReturnSuccess;
}
kern_return_t is_io_connect_get_service(mach_port_t connection, mach_port_t* service) {
    *service = MACH_PORT_NULL;
    if (auto* generic = dynamic_cast<ServiceUserConnection*>(IOObject::lookup(connection))) return generic->copyService(service);
    auto* client = dynamic_cast<PowerConnection*>(IOObject::lookup(connection));
    if (!client || client->closed) return kIOReturnNotOpen;
    *service = client->domain->port();
    return KERN_SUCCESS;
}
kern_return_t is_io_service_add_interest_notification_64(mach_port_t service, io_name_t interest,
    mach_port_t wake, io_async_ref64_t reference, mach_msg_type_number_t count, mach_port_t* notification) {
    *notification = MACH_PORT_NULL;
    auto* domain = dynamic_cast<IOPowerRootDomain*>(IOObject::lookup(service));
    kern_return_t result = kIOReturnUnsupported;
    if (domain && std::strcmp(interest, kIOAppPowerStateInterest) == 0) {
        if (!MACH_PORT_VALID(wake) || count != kIOInterestCalloutCount || reference[kIOInterestCalloutFuncIndex] == 0)
            result = kIOReturnBadArgument;
        else {
            auto* token = new PowerInterest(domain, wake, reference, count);
            *notification = token->port();
            token->releaseLater();
            return KERN_SUCCESS;
        }
    }
    // Errors are destroyed by MIG; successful requests transfer ownership here.
    return result;
}
