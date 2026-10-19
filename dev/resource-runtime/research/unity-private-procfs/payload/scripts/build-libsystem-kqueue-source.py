#!/usr/bin/env python3
"""Compile the complete libSystem initializer and Darling libkqueue sources."""
from pathlib import Path
import hashlib
import json
import re
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
darling = root / 'vendor/darling'
system = darling / 'src/external/libsystem'
queue = darling / 'src/external/libkqueue'
assert subprocess.check_output(['git', '-C', str(system), 'rev-parse', 'HEAD'], text=True).strip() == '08df454b6eb0df9400aa4c39839a7efd6efd2c3c'
folder = Path(tempfile.mkdtemp(prefix='libsystem-kqueue-source-', dir=root / 'runtime'))
generated = folder / 'include'
system_headers = generated / 'System'
system_headers.mkdir(parents=True)
for base in [darling / 'src/external/xnu/osfmk', darling / 'src/external/xnu/bsd']:
    for path in base.iterdir():
        target = system_headers / path.name
        if path.is_dir() and not target.exists():
            target.symlink_to(path, target_is_directory=True)
sdk = darling / 'Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
resource = Path(subprocess.check_output(['clang-19', '-print-resource-dir'], text=True).strip())
apple = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
server = root / 'runtime/darlingserver-source-build'
includes = [generated, system, queue / 'src/common', queue / 'include', darling / 'src/external/xnu',
    server / 'include', server / 'darlingserver/include', root / 'vendor/darlingserver/include',
    darling / 'src/external/xnu/darling/src/libsystem_kernel/emulation/include/linux_premigration/ext',
    sdk / 'usr/include', resource / 'include', darling / 'src/external/xnu/EXTERNAL_HEADERS']
common = ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-nostdinc',
    *['-I' + str(p) for p in includes], '-idirafter', str(apple / 'usr/include'),
    '-DPLATFORM_MacOSX=1', '-DDARLING=1', '-DHAVE_STDINT_H=1', '-DHAVE_SYSTEM_CORESERVICES=1', '-DPRIVATE=1',
    '-fblocks', '-fPIC', '-O0', '-g', '-Wno-incompatible-pointer-types', '-Wno-int-conversion',
    '-Wno-nullability-completeness', '-Wno-macro-redefined', '-Wno-deprecated-declarations']
sources = [system / name for name in ['init.c', 'darling/src/dummy.c', 'CompatibilityHacks.c']]
queue_sources = [queue / 'src/posix/platform.c']
queue_sources += [queue / ('src/linux/' + name + '.c') for name in
    ['platform', 'signal', 'socket', 'timer', 'user', 'vnode', 'write', 'read', 'proc', 'machport', 'fs']]
queue_sources += [queue / ('src/common/' + name + '.c') for name in ['filter', 'knote', 'map', 'kevent', 'kqueue']]
queue_sources += sorted((queue / 'src/darling').glob('*.c'))
# CMake file(GLOB) ignores optional source names absent from this revision.
queue_sources = [p for p in queue_sources if p.is_file()]
sources += queue_sources
commands = []
for i, source in enumerate(sources):
    obj = folder / (str(i) + '-' + source.stem + '.o')
    command = [*common, *(['-include', 'stdint.h', '-include', str(sdk / 'usr/include/sys/event.h'),
        '-D__linux__', '-D_DARWIN_C_SOURCE=1', '-D_XOPEN_SOURCE=600', '-DHAVE_SYS_EVENTFD_H=1',
        '-DHAVE_SYS_SIGNALFD_H=1', '-DHAVE_SYS_TIMERFD_H=1', '-std=c99', '-fvisibility=hidden']
        if source in queue_sources else []), '-c', str(source), '-o', str(obj),
        '-MMD', '-MF', str(folder / (str(i) + '.d'))]
    commands.append(command)
    print('COMPILE', source.relative_to(root), flush=True)
    subprocess.run(command, cwd=root, check=True)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
dependencies = set()
for dep in folder.glob('*.d'):
    dependencies.update(Path(p).resolve() for p in shlex.split(dep.read_text().split(':', 1)[1].replace('\\\n', ' ')))
record = dict(dependency_sha256={str(p.relative_to(root)) if p.is_relative_to(root) else str(p): sha(p) for p in sorted(dependencies)},
    object_sha256={str(p.relative_to(root)): sha(p) for p in folder.glob('*.o')},
    complete_source_objects=len(sources), full_initializer_and_queue_sources_compiled=True,
    commands=commands, objects=[str((folder / (str(i) + '-' + source.stem + '.o')).relative_to(root)) for i, source in enumerate(sources)],
    sources={str(p.relative_to(root)): sha(p) for p in [Path(__file__), system / 'CMakeLists.txt', queue / 'CMakeLists.txt', *sources]},
    linked=False, runtime_execution_verified=False)
(folder / 'objects.json').write_text(json.dumps(record, indent=2) + '\n')
print('OBJECT_REPORT', folder / 'objects.json', flush=True)
