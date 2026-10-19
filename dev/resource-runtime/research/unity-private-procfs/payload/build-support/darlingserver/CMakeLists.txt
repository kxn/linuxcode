cmake_minimum_required(VERSION 3.19)
project(linuxcode_darlingserver_source LANGUAGES C CXX ASM)
get_filename_component(PROJECT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(DARLING_SOURCE "${PROJECT_ROOT}/vendor/darling")
set(SERVER_SOURCE "${PROJECT_ROOT}/vendor/darlingserver")
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_EXTENSIONS ON)
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wno-error=implicit-function-declaration")
set(APPLE_ARCH_PRIMARY x86_64)
set(APPLE_TARGET_TRIPLET_PRIMARY x86_64-apple-darwin11)
list(APPEND CMAKE_MODULE_PATH "${DARLING_SOURCE}/cmake")
include(mig)
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/src/startup")
add_executable(rtsig "${DARLING_SOURCE}/src/startup/rtsig.c")
add_custom_command(OUTPUT "${CMAKE_BINARY_DIR}/src/startup/rtsig.h"
    COMMAND rtsig "${CMAKE_BINARY_DIR}/src/startup/rtsig.h" DEPENDS rtsig)
add_custom_target(rtsig_h DEPENDS "${CMAKE_BINARY_DIR}/src/startup/rtsig.h")
set(CMAKE_INSTALL_PREFIX /usr)
set(CMAKE_INSTALL_LIBDIR lib)
set(GIT_BRANCH source-experiment)
execute_process(COMMAND git -C "${SERVER_SOURCE}" rev-parse --short=7 HEAD
    OUTPUT_VARIABLE GIT_COMMIT_HASH OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
configure_file("${DARLING_SOURCE}/src/include/darling-config.h.in"
    "${CMAKE_BINARY_DIR}/include/darling-config.h")
include_directories("${CMAKE_BINARY_DIR}/include")
add_compile_definitions(DARLING=1 _GNU_SOURCE=1)
add_subdirectory("${DARLING_SOURCE}/src/external/bootstrap_cmds" bootstrap_cmds)
target_include_directories(migcom PRIVATE "${DARLING_SOURCE}/basic-headers")
# glibc already declares u_int; the bootstrap project's old macro would turn
# that system typedef into an invalid declaration on current Debian headers.
target_compile_options(migcom PRIVATE -Uu_int -include sys/types.h)
add_subdirectory("${DARLING_SOURCE}/src/libsimple" libsimple)
add_subdirectory("${SERVER_SOURCE}" darlingserver)
