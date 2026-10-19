#!/usr/bin/env python3
"""Execute shared-remap content/lifetime checks and existing memory-entry tests."""
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
parser.add_argument('--runtime-profile', default='scripts/shared-remap-runtime-profile.py')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='shared-remap-native-test-', dir=root / 'runtime'))
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
linkroot = root / 'runtime/rootfs/usr/libexec/darling'
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](stage=args.stage)
env = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    env.pop(key, None)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
cases = []
sources = [Path(__file__), root / 'fixtures/hello/memory-entry-test-utils.h']
for name, marker in [
    ('shared-remap', 'SHARED_REMAP_GROW_STITCH_NESTED_OFFSETS_ALIAS_LIFETIME_ADDRESS_REUSE_PROTECTIONS_ROUNDING_ERRORS_FD_CLEANUP_OK'),
    ('memory-entry-source', 'MEMORY_ENTRY_SOURCE_ADDRESS_REUSE_INVALID_CAPABILITIES_FLAGS_BOUNDS_AND_32_CONCURRENT_MAPS_OK')]:
    source = root / ('fixtures/hello/' + name + '.c')
    sources.append(source)
    obj, binary = folder / (name + '.o'), folder / name
    commands = [
        ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-g', '-c', str(source), '-o', str(obj)],
        ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(linkroot), '-lSystem', str(obj), '-o', str(binary)]]
    with (folder / (name + '-build.log')).open('w') as stream:
        for command in commands:
            subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, check=True)
    guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
    script = folder / (name + '.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\n' + shlex.join([guest(binary)]) +
        '\nstatus=$?\nprintf "SHARED_REMAP_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = p['command'][:-2] + ['/usr/bin/env', '-u', 'DISPLAY', '-u', 'WAYLAND_DISPLAY', '-u', 'XAUTHORITY', '/bin/bash', guest(script)]
    command[3] = '90'
    log = folder / (name + '.log')
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    output = log.read_text()
    native = re.findall(r'^SHARED_REMAP_NATIVE_STATUS (\d+)$', output, re.M)
    verified = result.returncode == 0 and native == ['0'] and marker in output
    cases.append(dict(name=name, verified=verified, compile_commands=commands, command=command,
        outer_status=result.returncode, native_status=native, marker=marker))
    print(name, verified, '\n', output[-3500:], flush=True)
record = dict(verified=all(c['verified'] for c in cases), stage=args.stage, runtime_profile=args.runtime_profile,
    stage_sha256=sha(root / args.stage), cases=cases, original_runtime_feature_disabled=False,
    full_VM_semantics_verified=False, full_Unity_build_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [*sources, *folder.iterdir()] if path.is_file()})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json', flush=True)
raise SystemExit(0 if record['verified'] else 1)
