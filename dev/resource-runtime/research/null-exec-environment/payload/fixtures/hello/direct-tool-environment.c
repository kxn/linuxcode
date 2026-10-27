#include <assert.h>
#include <errno.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;
static const char base_framework[] = "/tmp/baseline framework:=keep";
static const char base_library[] = "/tmp/baseline library:=keep";
static const char scoped_framework[] = "/tmp/scoped framework:/tmp/第二目录=值";
static const char scoped_library[] = "/tmp/scoped library:/tmp/第三目录=值";

static uint64_t bytes_hash(char** vector) {
    uint64_t hash = 1469598103934665603ULL;
    for (unsigned i = 0; vector[i]; ++i)
        for (size_t j = 0; j <= strlen(vector[i]); ++j)
            hash = (hash ^ (unsigned char)vector[i][j]) * 1099511628211ULL;
    return hash;
}

static void child(const char* path, char** envp, const char* frameworks, const char* libraries, int spawn) {
    char* arguments[] = {(char*)path, "--child", (char*)frameworks, (char*)libraries, NULL};
    uint64_t before = bytes_hash(envp);
    pid_t pid = -1;
    if (spawn) {
        assert(posix_spawn(&pid, path, NULL, NULL, arguments, envp) == 0);
    } else {
        pid = fork(); assert(pid >= 0);
        if (!pid) { execve(path, arguments, envp); _exit(127); }
    }
    int status;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    assert(before == bytes_hash(envp));
}

int main(int argc, char** argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 4 && !strcmp(argv[1], "--child")) {
        const char* fw = getenv("DYLD_FRAMEWORK_PATH");
        const char* lib = getenv("DYLD_LIBRARY_PATH");
        if (!fw || !lib || strcmp(fw, argv[2]) || strcmp(lib, argv[3])) {
            printf("DIRECT_SCOPE_WRONG framework=%s library=%s\n", fw ? fw : "(absent)", lib ? lib : "(absent)");
            return 1;
        }
        assert(!strcmp(getenv("DIRECT_SCOPE_PAYLOAD"), "literal $() `text`; UTF8=值"));
        puts("DIRECT_SCOPE_CHILD_EXACT_ENVIRONMENT_OK");
        return 0;
    }
    assert(argc == 4);
    unsigned count = 0;
    while (environ[count]) ++count;
    char** envp = calloc(count + 12, sizeof(char*)); assert(envp);
    unsigned used = 0;
    for (unsigned i = 0; i < count; ++i) {
        if (!strncmp(environ[i], "DYLD_FRAMEWORK_PATH=", 20) || !strncmp(environ[i], "DYLD_LIBRARY_PATH=", 18)
            || !strncmp(environ[i], "DARLING_DYLD_OVERRIDE_", 22) || !strncmp(environ[i], "DIRECT_SCOPE_PAYLOAD=", 21)) continue;
        envp[used++] = environ[i];
    }
    char frameworks[1024], libraries[1024], targets[4096], override_fw[1024], override_lib[1024];
    snprintf(frameworks, sizeof(frameworks), "DYLD_FRAMEWORK_PATH=%s", base_framework);
    snprintf(libraries, sizeof(libraries), "DYLD_LIBRARY_PATH=%s", base_library);
    assert(snprintf(targets, sizeof(targets), "DARLING_DYLD_OVERRIDE_EXECUTABLES=/tmp/not-selected:%s:", argv[1]) < sizeof(targets));
    snprintf(override_fw, sizeof(override_fw), "DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH=%s", scoped_framework);
    snprintf(override_lib, sizeof(override_lib), "DARLING_DYLD_OVERRIDE_LIBRARY_PATH=%s", scoped_library);
    envp[used++] = frameworks; envp[used++] = libraries;
    envp[used++] = "DIRECT_SCOPE_PAYLOAD=literal $() `text`; UTF8=值";
    unsigned configured = used;
    envp[used++] = targets; envp[used++] = override_fw; envp[used++] = override_lib;
    for (int spawn = 0; spawn <= 1; ++spawn) {
        child(argv[1], envp, scoped_framework, scoped_library, spawn);
        child(argv[2], envp, base_framework, base_library, spawn);
        child(argv[3], envp, base_framework, base_library, spawn);
    }
    envp[configured+1] = override_lib; envp[configured+2] = NULL;
    child(argv[1], envp, base_framework, scoped_library, 1);
    strcpy(override_fw, "DARLING_DYLD_OVERRIDE_FRAMEWORK_PATH=");
    envp[configured+1] = override_fw;
    child(argv[1], envp, "", base_library, 1);
    envp[configured] = NULL;
    child(argv[1], envp, base_framework, base_library, 1);
    envp[configured] = targets; envp[configured+1] = override_lib;
    uint64_t before = bytes_hash(envp);
    char* absent[] = {"/tmp/absent-direct-scope-tool", NULL};
    errno = 0;
    assert(execve(absent[0], absent, envp) == -1 && errno == ENOENT);
    assert(before == bytes_hash(envp));
    free(envp);
    puts("DIRECT_SCOPE_EXEC_SPAWN_EXACT_PATH_UTF8_EMPTY_VALUES_PARENT_UNCHANGED_AND_ENOENT_OK");
    return 0;
}
