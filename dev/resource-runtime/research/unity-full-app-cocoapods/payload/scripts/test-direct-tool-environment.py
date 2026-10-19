#!/usr/bin/env python3
"""Run the same native per-executable environment checks on an old or new complete runtime."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='direct-tool-environment-test-', dir=root / 'runtime'))
source = root / 'fixtures/hello/direct-tool-environment.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guestroot = root / 'runtime/rootfs/usr/libexec/darling'
obj, binary = folder / 'probe.o', folder / 'probe'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(guestroot), '-lSystem', str(obj), '-o', str(binary)]]
with (folder / 'build.log').open('w') as out:
    for command in commands:
        subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT, check=True)
helpers = [folder / name for name in ['resource tool=测试', 'resource tool=测试.neighbor', 'unrelated']]
for helper in helpers:
    shutil.copy2(binary, helper)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary), *map(guest, helpers)]) +
    '\nstatus=$?\nprintf "DIRECT_SCOPE_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
module = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))
p = module['profile'](stage=args.stage)
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
command = p['command'][:-2] + ['/usr/bin/env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY', '-u', 'XAUTHORITY', '/bin/bash', guest(script)]
command[3] = '90'
with (folder / 'run.log').open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
text = (folder / 'run.log').read_text()
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
verified = result.returncode == 0 and 'DIRECT_SCOPE_EXEC_SPAWN_EXACT_PATH_UTF8_EMPTY_VALUES_PARENT_UNCHANGED_AND_ENOENT_OK' in text and 'DIRECT_SCOPE_NATIVE_STATUS 0' in text
record = dict(verified=verified, outer_status=result.returncode, stage=args.stage, commands=commands, command=command,
    child_successes=text.count('DIRECT_SCOPE_CHILD_EXACT_ENVIRONMENT_OK'),
    original_actool_or_ibtool_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, root / args.stage, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text, 'EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
