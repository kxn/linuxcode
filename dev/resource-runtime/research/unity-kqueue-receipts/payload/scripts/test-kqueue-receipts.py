#!/usr/bin/env python3
"""Exercise real receipt/error/readiness behavior through both kevent ABIs."""
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
folder = Path(tempfile.mkdtemp(prefix='kqueue-receipts-test-', dir=root / 'runtime'))
source = root / 'fixtures/hello/kqueue-receipts.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guestroot = root / 'runtime/rootfs/usr/libexec/darling'
binary, obj = folder / 'probe', folder / 'probe.o'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(guestroot), '-lSystem', str(obj), '-o', str(binary)]]
with (folder / 'build.log').open('w') as stream:
    for command in commands:
        subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, cwd=root, check=True)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary)]) +
    '\nstatus=$?\nprintf "KQUEUE_RECEIPTS_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
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
verified = result.returncode == 0 and 'KQUEUE_RECEIPTS_ERRORS_MULTICHANGE_AND_REAL_READINESS_OK' in output and 'KQUEUE_RECEIPTS_NATIVE_STATUS 0' in output
record = dict(verified=verified, outer_status=result.returncode, runtime_profile=args.runtime_profile, stage=args.stage, commands=commands,
    command=command, full_Unity_build_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, root / args.stage, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(output, 'EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
