// A real per-opening Mach user-client connection to an existing service.
#ifndef DARLING_SERVICE_USER_CONNECTION_H
#define DARLING_SERVICE_USER_CONNECTION_H
#include "IOUserClient.h"
#include "iokitd.h"
#include <IOKit/IOReturn.h>
class ServiceUserConnection final : public IOUserClient {
    IOUserClient* m_service;
    pid_t m_owner;
    bool m_closed = false;
public:
    ServiceUserConnection(IOUserClient* service, pid_t owner) : m_service(service), m_owner(owner) { m_service->retain(); }
    ~ServiceUserConnection() override { m_service->release(); }
    const char* className() const override { return "IOUserClient"; }
    NSDictionary* matchingDictionary() override { return @{}; }
    IOReturn validateCaller() const override {
        if (m_closed) return kIOReturnNotOpen;
        return g_iokitCurrentCallerPID == m_owner ? kIOReturnSuccess : kIOReturnNotPermitted;
    }
    IOExternalMethod* getExternalMethodForIndex(UInt32 index) override {
        return validateCaller() == kIOReturnSuccess ? m_service->getExternalMethodForIndex(index) : nullptr;
    }
    IOReturn close() {
        auto result = validateCaller();
        if (result == kIOReturnSuccess) m_closed = true;
        return result;
    }
    IOReturn copyService(mach_port_t* result) {
        auto status = validateCaller();
        if (status == kIOReturnSuccess) *result = m_service->port();
        return status;
    }
};
#endif
