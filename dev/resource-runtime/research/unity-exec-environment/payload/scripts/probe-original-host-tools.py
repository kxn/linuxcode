#!/usr/bin/env python3
"""Check the absolute original plutil command and typed plist output."""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-host-tools-test-', dir=root / 'runtime'))
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
values = dict(Text='雪 $(literal)', Empty='', Integer=2**40+7, Flag=True,
    Data=bytes([0, 1, 255]), Items=['one', 42, False], Nested=dict(flag=False))
source, output = folder / 'input.plist', folder / 'output.plist'
source.write_bytes(plistlib.dumps(values))
version = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/version.plist'
expected_version = plistlib.loads(version.read_bytes())['CFBundleShortVersionString']
commands = [
    ['/usr/bin/plutil', '-extract', 'CFBundleShortVersionString', 'raw', '-o', guest(folder / 'version.txt'), '/Applications/Xcode.app/Contents/version.plist'],
    ['/usr/bin/plutil', '-convert', 'binary1', '-o', guest(output), guest(source)],
    ['/usr/bin/plutil', '-extract', 'Nested.flag', 'raw', '-o', guest(folder / 'flag.txt'), guest(source)]]
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\nset -e\n' +
    '\n'.join(shlex.join(command) for command in commands) + '\nprintf "ORIGINAL_HOST_TOOLS_NATIVE_STATUS 0\\n"\n')
module = runpy.run_path(str(root / 'scripts/loader-environment-runtime-profile.py'))
p = module['profile'](args.stage)
command = p['command'][:-2] + ['/bin/bash', guest(script)]
command[3] = '60'
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
with (folder / 'run.log').open('w') as stream:
    result = subprocess.run(command, env=env, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
text = (folder / 'run.log').read_text()
verified = result.returncode == 0 and 'ORIGINAL_HOST_TOOLS_NATIVE_STATUS 0' in text
if verified:
    decoded = plistlib.loads(output.read_bytes())
    verified = output.read_bytes().startswith(b'bplist00') and decoded == values
    verified &= type(decoded['Integer']) is int and type(decoded['Flag']) is bool and type(decoded['Data']) is bytes
    verified &= (folder / 'version.txt').read_text().strip() == expected_version
    verified &= (folder / 'flag.txt').read_text().strip() == 'false'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
record = dict(verified=bool(verified), stage=args.stage, outer_status=result.returncode,
    command=command, original_commands=commands, expected_version=expected_version,
    independent_typed_binary_plist_verified=bool(verified), full_Unity_build_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in
        [Path(__file__), root / args.stage, version, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(text, 'EVIDENCE', folder / 'result.json', 'VERIFIED', verified)
raise SystemExit(0 if verified else 1)
