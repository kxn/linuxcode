#include <darlingserver/file-signatures.hpp>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <string>
#include <unistd.h>

int main(int argc, char** argv) {
    if (argc != 5 && argc != 6) return 64;
    int fd = open(argv[1], O_RDONLY | O_CLOEXEC);
    uint64_t covered = UINT64_MAX;
    std::string reason;
    auto check = argc==6 ? DarlingServer::FileSignatures::registerEmbeddedFile : DarlingServer::FileSignatures::registerSimulatorDyld;
    int error = check(fd,
        strtoull(argv[2], nullptr, 0), strtoull(argv[3], nullptr, 0),
        strtoull(argv[4], nullptr, 0), covered, &reason);
    if (fd >= 0) close(fd);
    printf("error=%d covered=%llu reason=%s\n", error,
        (unsigned long long)covered, reason.c_str());
    return error ? 1 : 0;
}
