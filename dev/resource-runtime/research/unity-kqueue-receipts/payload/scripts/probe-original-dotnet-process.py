#!/usr/bin/env python3
"""Inspect and execute uname through the original Unity .NET process backend."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--runtime-profile', default='scripts/libsystem-kqueue-runtime-profile.py')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-dotnet-process-', dir=root / 'runtime'))
source = root / 'fixtures/hello/original-dotnet-process.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guestroot = root / 'runtime/rootfs/usr/libexec/darling'
binary, obj = folder / 'probe', folder / 'probe.o'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(guestroot), '-lSystem', str(obj), '-o', str(binary)]]
with (folder / 'build.log').open('w') as stream:
    for command in commands:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, cwd=root, check=True)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
library = root / 'runtime/unity-uemuera-device-export/ios/Il2CppOutputProject/IL2CPP/build/deploy_x86_64/libSystem.Native.dylib'
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary), guest(library)]) +
    '\nstatus=$?\nprintf "DOTNET_PROCESS_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](stage=args.stage)
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
command = p['command'][:-2] + ['/usr/bin/env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY', '-u', 'XAUTHORITY', '/bin/bash', guest(script)]
command[3] = '60'
with (folder / 'run.log').open('w') as stream:
    result = subprocess.run(command, env=env, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
output = (folder / 'run.log').read_text()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
verified = result.returncode == 0 and 'ORIGINAL_DOTNET_PROCESS_UNAME_STAT_SPAWN_AND_OUTPUT_OK' in output and 'DOTNET_PROCESS_NATIVE_STATUS 0' in output
record = dict(verified=verified, outer_status=result.returncode, runtime_profile=args.runtime_profile, stage=args.stage, commands=commands,
    command=command, full_Unity_build_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, library, root / args.stage, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(output, 'EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
