#!/usr/bin/env python3
"""Build the complete Linux x86_64 Mach-O loader in a new private directory."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = root / 'vendor/darling/src/startup/mldr'
generated = root / 'runtime/darlingserver-source-build'
server = root / 'vendor/darlingserver'
folder = Path(tempfile.mkdtemp(prefix='mldr-source-', dir=root / 'runtime'))
common = ['clang-19', '-D_GNU_SOURCE=1', '-DMLDR_BUILD=1', '-DINSTALL_PREFIX="/usr"',
    '-std=gnu11', '-O2', '-g', '-pthread', '-fno-strict-aliasing',
    '-I' + str(source / 'include'), '-I' + str(source),
    '-I' + str(root / 'vendor/darling/src/external/xnu/EXTERNAL_HEADERS'),
    '-I' + str(generated / 'include'),
    '-I' + str(generated / 'darlingserver/include'), '-I' + str(server / 'include'),
    '-I' + str(generated / 'src/startup')]
sources = [source / name for name in ['mldr.c', 'commpage.c', 'elfcalls/elfcalls.c', 'elfcalls/threads.c']]
rpc = generated / 'darlingserver/src/rpc.c'
commands = []
for i, path in enumerate([*sources, rpc]):
    obj = folder / (str(i) + '.o')
    command = [*common, *(['-include', str(source / 'resources/dserver-rpc-defs.h')] if path == rpc else []),
        '-c', str(path), '-o', str(obj), '-MMD', '-MF', str(folder / (str(i) + '.d'))]
    commands.append(command)
    subprocess.run(command, check=True, cwd=root)
command = ['clang-19', '-pthread', *[str(folder / (str(i) + '.o')) for i in range(5)],
    '-lrt', '-ldl', '-lm', '-o', str(folder / 'mldr')]
commands.append(command)
subprocess.run(command, check=True, cwd=root)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
inputs = {Path(__file__)}
for dep in folder.glob('*.d'):
    # All project paths in this build are space-free; escaped continuations
    # are compiler-generated. System headers are supplied by the host toolchain.
    for item in dep.read_text().replace('\\\n', '').split(':', 1)[1].split():
        path = Path(item)
        assert path.is_file(), path
        inputs.add(path)
record = dict(full_mldr_source_build=True, architecture='Linux x86_64',
    installed=False, runtime_execution_verified=False, folder=str(folder.relative_to(root)),
    loader=str((folder / 'mldr').relative_to(root)), loader_sha256=sha(folder / 'mldr'),
    commands=commands, files={str(p.relative_to(root)): sha(p) for p in sorted(inputs)})
(folder / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
print('BUILD_REPORT', folder / 'build.json', flush=True)
