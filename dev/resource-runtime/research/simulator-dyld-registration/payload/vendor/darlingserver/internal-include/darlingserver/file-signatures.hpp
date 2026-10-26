// Descriptor-based simulator dyld signature registration for Linux hosts.
#pragma once
#include <cstdint>
#include <string>
namespace DarlingServer::FileSignatures {
// Returns a Linux errno value, or zero with the signed slice coverage.
// This implements the bounded command-83 path, not general AMFI enforcement.
int registerSimulatorDyld(int fd, uint64_t sliceStart, uint64_t blobStart,
    uint64_t blobSize, uint64_t& coveredLength, std::string* reason = nullptr);
}
