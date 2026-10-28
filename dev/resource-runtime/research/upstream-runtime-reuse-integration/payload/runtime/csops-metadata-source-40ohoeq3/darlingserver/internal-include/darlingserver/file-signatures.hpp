// Descriptor-based simulator dyld signature registration for Linux hosts.
#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include <array>
namespace DarlingServer::FileSignatures {
// Actual descriptor metadata; valid means verified file coverage, not AMFI,
// platform identity, trust-chain approval, or entitlement enforcement.
struct ExecutableMetadata {
    bool valid = false;
    uint32_t flags = 0;
    uint64_t slice = 0;
    std::array<unsigned char, 20> cdhash{};
    std::vector<unsigned char> directory, blob, xml, der;
    std::string identifier, team;
};
// Match the FAT slice and every load command to the loaded executable before
// verifying its code pages and signed metadata. Unsigned files return valid=false.
int executableMetadata(int fd, const std::vector<unsigned char>& live,
    ExecutableMetadata& result, std::string* reason = nullptr);
// Returns a Linux errno value, or zero with the signed slice coverage.
// This implements the bounded command-83 path, not general AMFI enforcement.
int registerSimulatorDyld(int fd, uint64_t sliceStart, uint64_t blobStart,
    uint64_t blobSize, uint64_t& coveredLength, std::string* reason = nullptr);
// F_ADDFILESIGS_RETURN registers code coverage, not platform identity. Accept
// a verified Apple-rooted code-signing CMS or a correctly hashed ad-hoc CD.
int registerEmbeddedFile(int fd, uint64_t sliceStart, uint64_t blobStart,
    uint64_t blobSize, uint64_t& coveredLength, std::string* reason = nullptr);
}
