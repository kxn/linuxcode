#!/usr/bin/env python3
"""Compare Darwin boot time and monotonic elapsed time with independent inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='boottime-clock-', dir=root/'runtime'))
source = root/'fixtures/hello/boottime-clock.c'
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
obj, binary = folder/'probe.o', folder/'probe'
commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(sdk), '-lSystem', str(obj), '-o', str(binary)]]
for command in commands: subprocess.run(command, check=True)
expected = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')))
module = runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p = module['profile'](stage=args.stage)
command = p['command'][:-2] + ['/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root)), str(expected)]
command[3] = '30'
env = module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']: env.pop(name, None)
log = folder/'run.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
text = log.read_text()
verified = result.returncode == 0 and 'KERN_BOOTTIME_LINUX_EPOCH_96_SAMPLES_BUFFER_GUARDS_AND_MONOTONIC_MACH_CLOCK_OK' in text
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
record = dict(verified=verified, outer_status=result.returncode, expected_linux_btime=expected,
    stage=args.stage, command=command, build_commands=commands, source_runtime=p['source_runtime'],
    log=str(log.relative_to(root)), log_sha256=sha(log),
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), source, binary, root/args.stage]},
    CoreSimulator_service_wait_causality_verified=False)
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text[-1800:])
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if verified else 1)
