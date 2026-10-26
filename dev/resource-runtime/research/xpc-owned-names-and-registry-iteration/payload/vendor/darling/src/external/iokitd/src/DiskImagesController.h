// Darling's registry for disk images attached through its own image backend.
// The current backend has no attach implementation, so it starts with no media.
// IOServiceOpen remains unsupported; this must not advertise successful mounts.
#ifndef DARLING_DISK_IMAGES_CONTROLLER_H
#define DARLING_DISK_IMAGES_CONTROLLER_H
#include "IOService.h"
#include "ServiceRegistry.h"
#include <Foundation/NSString.h>
#include <Foundation/NSNumber.h>

class DiskImagesController final : public IOService {
    const char* m_className;
    explicit DiskImagesController(const char* name) : m_className(name) {}
public:
    const char* className() const override { return m_className; }
    NSDictionary* matchingDictionary() override {
        return @{ @"IOClass": [NSString stringWithUTF8String:m_className] };
    }
    NSDictionary* getProperties() override {
        return @{ @"IOClass": [NSString stringWithUTF8String:m_className],
                  @"DarlingDiskImagesBackend": @"Darling managed images",
                  @"DarlingDiskImagesSupportsAttach": @NO };
    }
    static void registerSelf(ServiceRegistry* registry) {
        // The two generations enumerate distinct managed-media namespaces.
        for (const char* name : {"AppleDiskImagesController", "IOHDIXController"}) {
            auto* controller = new DiskImagesController(name);
            controller->registerInPlane(kIOServicePlane, name, IORegistryEntry::root());
            registry->registerService(controller);
            controller->release();
        }
    }
};
#endif
