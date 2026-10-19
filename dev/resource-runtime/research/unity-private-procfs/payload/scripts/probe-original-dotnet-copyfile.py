#!/usr/bin/env python3
"""Compare original .NET file copies and Darwin sparse seeks to Linux byte/extent oracles."""
from pathlib import Path
import argparse
import errno
import hashlib
import json
import os
import re
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--runtime-profile', default='scripts/private-procfs-runtime-profile.py')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-dotnet-copyfile-', dir=root / 'runtime'))
source = root / 'fixtures/hello/original-dotnet-copyfile.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guestroot = root / 'runtime/rootfs/usr/libexec/darling'
binary, obj = folder / 'probe', folder / 'probe.o'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(guestroot), '-lSystem', str(obj), '-o', str(binary)]]
with (folder / 'build.log').open('w') as out:
    for command in commands:
        subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT, check=True)
dense, sparse, empty = [folder / name for name in ['dense.bin', 'sparse.bin', 'empty.bin']]
dense.write_bytes(bytes(range(256))*64+b'final unaligned bytes')
with sparse.open('wb') as out:
    out.seek(4096); out.write(bytes(range(256))*16)
    out.seek(4*4096); out.write(b'last data')
    out.truncate(8*4096)
empty.touch()
inputs = [dense, sparse, empty]
oracle = []
for i, path in enumerate(inputs):
    with path.open('rb') as stream:
        # Stabilize delayed allocation before comparing extent queries made
        # later by another process. The bytes are unchanged by this sync.
        os.fsync(stream.fileno())
        for offset in [-1, 0, 4096, path.stat().st_size]:
            for kind, whence in [('data', os.SEEK_DATA), ('hole', os.SEEK_HOLE)]:
                try:
                    value, error = os.lseek(stream.fileno(), offset, whence), 0
                except OSError as caught:
                    value, error = -1, caught.errno
                assert error in (0, errno.ENXIO, errno.EINVAL)
                oracle.append(dict(file=i, offset=offset, kind=kind, result=value, errno=error))
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
library = root / 'runtime/unity-uemuera-device-export/ios/Il2CppOutputProject/IL2CPP/build/deploy_x86_64/libSystem.Native.dylib'
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary), guest(library), *map(guest, inputs)]) +
    '\nstatus=$?\nprintf "COPYFILE_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](stage=args.stage)
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
command = p['command'][:-2] + ['/usr/bin/env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY', '-u', 'XAUTHORITY', '/bin/bash', guest(script)]
command[3] = '60'
with (folder / 'run.log').open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
text = (folder / 'run.log').read_text()
actual = [dict(file=int(i), offset=int(o), kind=k, result=int(v), errno=int(e)) for i,o,k,v,e in
    re.findall(r'^SEEK file=(\d+) offset=(-?\d+) kind=(data|hole) result=(-?\d+) errno=(\d+)$', text, re.M)]
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
copies = []
for path in inputs:
    for suffix in ['.copy', '.sparsecopy']:
        target = path.with_suffix(path.suffix+suffix)
        copies.append(dict(source=str(path.relative_to(root)), destination=str(target.relative_to(root)),
            source_sha256=sha(path), destination_sha256=sha(target) if target.exists() else None,
            equal=target.exists() and path.read_bytes() == target.read_bytes()))
verified = result.returncode == 0 and 'COPYFILE_NATIVE_STATUS 0' in text and len(actual) == 24 and actual == oracle and all(row['equal'] for row in copies)
record = dict(verified=verified, outer_status=result.returncode, runtime_profile=args.runtime_profile,
    stage=args.stage, original_library=str(library.relative_to(root)), original_library_sha256=sha(library),
    commands=commands, command=command, seek_oracle=oracle, seek_actual=actual,
    sparse_seek_matches=actual == oracle, copies=copies, full_Unity_App_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, root / args.stage, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text, 'EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
