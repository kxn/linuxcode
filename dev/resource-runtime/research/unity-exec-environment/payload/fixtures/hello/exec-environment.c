#include <assert.h>
#include <errno.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include <crt_externs.h>

extern char** environ;
static char path[] = "PATH=/usr/bin:/bin";
static char value[] = "LINUXCODE_ENV_SENTINEL=literal $(value) 雪";
static char empty[] = "LINUXCODE_ENV_EMPTY=";
static char* child_environment[] = {path, value, empty, NULL};

static void check_child_environment(void) {
    char** env = *_NSGetEnviron();
    unsigned count = 0;
    while (env[count]) {
        assert(env[count][0] != '\0');
        assert(strncmp(env[count], "__mldr_", 7) != 0);
        assert(count < 3 && strcmp(env[count], child_environment[count]) == 0);
        count++;
    }
    assert(count == 3);
    assert(!strcmp(getenv("PATH"), path+5));
    assert(!strcmp(getenv("LINUXCODE_ENV_SENTINEL"), value+sizeof("LINUXCODE_ENV_SENTINEL=")-1));
    assert(getenv("LINUXCODE_ENV_EMPTY") && !*getenv("LINUXCODE_ENV_EMPTY"));
    assert(!getenv("__mldr_sockpath") && !getenv("__mldr_lifetime_pipe"));
}

int main(int argc, char** argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 3 && !strcmp(argv[1], "--child")) {
        check_child_environment();
        int depth = atoi(argv[2]);
        if (depth) {
            char next[16]; snprintf(next, sizeof(next), "%d", depth-1);
            char* arguments[] = {argv[0], "--child", next, NULL};
            execve(argv[0], arguments, environ);
            perror("recursive execve"); return 1;
        }
        puts("EXEC_ENVIRONMENT_CHILD_EXACT_BYTES_AND_NO_PRIVATE_OR_EMPTY_ENTRIES_OK");
        return 0;
    }
    assert(argc == 1);
    char* arguments[] = {argv[0], "--child", "6", NULL};
    pid_t child = fork(); assert(child >= 0);
    if (!child) {
        execve(argv[0], arguments, child_environment);
        perror("execve"); _exit(1);
    }
    int status = -1;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    assert(posix_spawn(&child, argv[0], NULL, NULL, arguments, child_environment) == 0);
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    errno = 0;
    assert(execve("/linuxcode/nonexistent/program", arguments, child_environment) == -1 && errno == ENOENT);
    assert(!strcmp(path, "PATH=/usr/bin:/bin") && !strcmp(empty, "LINUXCODE_ENV_EMPTY="));
    assert(!strcmp(value, "LINUXCODE_ENV_SENTINEL=literal $(value) 雪"));
    puts("EXEC_ENVIRONMENT_FORK_SPAWN_14_EXEC_GENERATIONS_AND_ERROR_OK");
    return 0;
}
