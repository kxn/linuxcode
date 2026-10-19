#!/usr/bin/env python3
"""Run a small managed environment/child-process probe on the unmodified Unity CoreCLR."""
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
parser.add_argument('--legacy-host-defaults', action='store_true', help='Reproduce the original diagnostic host settings without Unity runtimeconfig properties')
parser.add_argument('--runtime-profile', default='scripts/libsystem-kqueue-runtime-profile.py')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-coreclr-managed-environment-', dir=root / 'runtime'))
source = root / 'fixtures/hello/original-coreclr-host.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guestroot = root / 'runtime/rootfs/usr/libexec/darling'
binary, obj = folder / 'probe', folder / 'probe.o'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(guestroot), '-lSystem', str(obj), '-o', str(binary)]]
managed_source = root / 'fixtures/hello/ManagedProcessEnvironment.cs'
managed = folder / 'ManagedProcessEnvironment.exe'
commands.append(['mcs', '-out:' + str(managed), str(managed_source)])
with (folder / 'build.log').open('w') as stream:
    for command in commands:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, cwd=root, check=True)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
library = root / 'runtime/unity-uemuera-device-export/ios/Il2CppOutputProject/IL2CPP/build/deploy_x86_64/libSystem.Native.dylib'
runtime_config = library.parent / 'il2cpp.runtimeconfig.json'
properties = {} if args.legacy_host_defaults else json.loads(runtime_config.read_text())['runtimeOptions']['configProperties']
config_arguments = [part for key, value in properties.items() for part in (key, str(value).lower() if isinstance(value, bool) else str(value))]
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary), guest(library.parent), guest(managed), *config_arguments]) +
    '\nstatus=$?\nprintf "CORECLR_MANAGED_ENVIRONMENT_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](stage=args.stage)
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
command = p['command'][:-2] + ['/usr/bin/env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY', '-u', 'XAUTHORITY', 'LINUXCODE_BEE_DEPLOY=' + guest(library.parent), '/bin/bash', guest(script)]
command[3] = '60'
with (folder / 'run.log').open('w') as stream:
    result = subprocess.run(command, env=env, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
output = (folder / 'run.log').read_text()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
verified = result.returncode == 0 and 'ORIGINAL_CORECLR_MANAGED_ENVIRONMENT_AND_PATH_CHILD_OK' in output and 'CORECLR_MANAGED_ENVIRONMENT_NATIVE_STATUS 0' in output
record = dict(verified=verified, outer_status=result.returncode, original_runtime_config=str(runtime_config.relative_to(root)), runtime_properties=properties, runtime_profile=args.runtime_profile, stage=args.stage, commands=commands,
    command=command, full_Unity_build_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, managed_source, runtime_config, library, library.parent / "libcoreclr.dylib", root / args.stage, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(output, 'EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
