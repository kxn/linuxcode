/* Exercise original Apple linker's special oslog string section layout. */
__attribute__((used, section("__TEXT,__oslogstring,cstring_literals"), aligned(16384)))
static const volatile char oslog_probe[] = "linuxcode original linker page alignment";
int main(void) { return oslog_probe[0] == 'l' ? 0 : 1; }
