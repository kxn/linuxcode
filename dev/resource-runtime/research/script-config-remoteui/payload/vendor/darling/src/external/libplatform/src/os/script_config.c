/* Darling's x86_64 storage for the libplatform script-config SPI.
 * The caller owns initialization and protection, as in WebKit LLIntData.cpp.
 * Keep whole pages separate from unrelated writable data.
 */
#if defined(__x86_64__)
__attribute__((aligned(4096), used, visibility("default"),
               section("__DATA,__script_config")))
unsigned char os_script_config_storage[16384];
#endif
