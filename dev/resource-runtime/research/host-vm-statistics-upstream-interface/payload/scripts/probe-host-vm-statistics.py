#!/usr/bin/env python3
"""Compare original Mach host-memory APIs to measured Linux page counters."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', default='config/direct-resource-tool-environment-v154.json')
parser.add_argument('--expect-zero-stub', action='store_true')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='host-vm-statistics-', dir=root / 'runtime'))
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = root / 'fixtures/hello/host-vm-statistics.c'
binary = folder / 'probe'
commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O2', '-c', str(source), '-o', str(folder / 'probe.o')],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(sdk), '-lSystem', '-no_fixup_chains', '-no_adhoc_codesign', str(folder / 'probe.o'), '-o', str(binary)],
]
for command in commands:
    subprocess.run(command, check=True)
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
env = module['environment'](profile)
for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
    env.pop(name, None)
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary)] + (['baseline'] if args.expect_zero_stub else [])) + '\nstatus=$?\nprintf "HOST_VM_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
command = profile['command'][:-2] + ['/bin/bash', guest(script)]
command[3] = '60'
def snapshot():
    keys = ('MemTotal', 'MemFree', 'Active', 'Inactive', 'Unevictable')
    return {line.split(':', 1)[0]: int(line.split()[1]) * 1024
            for line in Path('/proc/meminfo').read_text().splitlines()
            if line.split(':', 1)[0] in keys}
before = snapshot()
log = folder / 'run.log'
print('RUNNING', folder.relative_to(root), flush=True)
with log.open('w') as output:
    result = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
after = snapshot()
text = log.read_text()
samples = re.findall(r'^HOST_VM_SAMPLE (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$', text, re.M)
reference_agrees = False
translated = {}
if samples:
    page, total, free, active, inactive, wired = map(int, samples[0])
    translated = dict(zip(('MemFree', 'Active', 'Inactive', 'Unevictable'), [value * page for value in (free, active, inactive, wired)]))
    # Startup and sequential requests sample a live host. Allow 2% of RAM or
    # 64 MiB beyond the enclosing snapshots; never accept an all-zero result.
    tolerance = max(total // 50, 64 * 1024 * 1024)
    reference_agrees = total == before['MemTotal'] == after['MemTotal'] and all(
        min(before[key], after[key]) - tolerance <= value <= max(before[key], after[key]) + tolerance
        for key, value in translated.items()) and active > 0
marker = 'HOST_VM_ZERO_STUB_REPRODUCED' if args.expect_zero_stub else 'HOST_VM_REVISION_AND_BUFFER_ABI_OK'
verified = result.returncode == 0 and re.findall(r'^HOST_VM_NATIVE_STATUS (\d+)$', text, re.M) == ['0'] and marker in text
if not args.expect_zero_stub:
    verified = verified and reference_agrees
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
report = dict(verified=verified, expected_zero_stub=args.expect_zero_stub, stage=args.stage,
              configuration=args.configuration, outer_status=result.returncode,
              before_bytes=before, after_bytes=after, translated_bytes=translated,
              reference_agrees=reference_agrees, compile_commands=commands, command=command,
              log=str(log.relative_to(root)), log_sha256=sha(log),
              files={str(path.relative_to(root)): sha(path) for path in (Path(__file__), source, binary)},
              limitation='Linux Unevictable maps only the userspace subset of Darwin wired pages; unsupported counters remain zero.',
              full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print('\n'.join(line for line in text.splitlines() if line.startswith('HOST_VM_')))
print('EVIDENCE', folder / 'result.json', flush=True)
raise SystemExit(0 if verified else 1)
