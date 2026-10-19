project(libsandbox)

set(DYLIB_INSTALL_NAME "/usr/lib/system/libsystem_sandbox.dylib")
set(sandbox_sources
	sandbox.c
	check.c
	extension.c
	extension_constants.c
)
add_circular(system_sandbox FAT
	SOURCES
	${sandbox_sources}

	SIBLINGS
		system_dyld
	DEPENDENCIES
		system_c
		system_kernel
		system_malloc
)

install(TARGETS system_sandbox DESTINATION libexec/darling/usr/lib/system)
