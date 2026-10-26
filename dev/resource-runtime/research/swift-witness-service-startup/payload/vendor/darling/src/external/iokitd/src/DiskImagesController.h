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
public:
    const char* className() const override { return "AppleDiskImagesController"; }
    NSDictionary* matchingDictionary() override {
        return @{ @"IOClass": @"AppleDiskImagesController" };
    }
    NSDictionary* getProperties() override {
        return @{ @"IOClass": @"AppleDiskImagesController",
                  @"DarlingDiskImagesBackend": @"Darling managed images",
                  @"DarlingDiskImagesSupportsAttach": @NO };
    }
    static void registerSelf(ServiceRegistry* registry) {
        auto* controller = new DiskImagesController;
        controller->registerInPlane(kIOServicePlane, "AppleDiskImagesController",
                                    IORegistryEntry::root());
        registry->registerService(controller);
        controller->release();
    }
};
#endif
