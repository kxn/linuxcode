#!/usr/bin/env python3
"""Compile or link with original Apple Clang directly and through original UBA."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import struct
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', default='config/direct-resource-tool-environment-v154.json')
parser.add_argument('--output-dir')
parser.add_argument('--compact-library-paths', action='store_true')
parser.add_argument('--operation', choices=('compile', 'link'), default='compile')
parser.add_argument('--source-file', help='Use this existing workspace source instead of the built-in tiny source')
parser.add_argument('--response-file', help='Use an existing original linker response file, preserving its contents')
parser.add_argument('--working-directory', help='Original response-file working directory')
parser.add_argument('--driver-only', action='store_true', help='Print original Clang -### expansion without executing the linker or UBA')
parser.add_argument('--extra-argument', action='append', default=[])
parser.add_argument('--library-directory', help='Prepend one private candidate provider directory to the caller library scope')
parser.add_argument('--capture-linker-snapshots', action='store_true', help='Copy linker snapshots into the private output before the session exits')
parser.add_argument('--timeout-seconds', type=int, default=180)
args = parser.parse_args()
assert 0 < args.timeout_seconds <= 7200
folder = (root / args.output_dir).resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix='original-uba-clang-', dir=root / 'runtime'))
assert folder.is_relative_to(root / 'runtime')
folder.mkdir(exist_ok=True)
assert not (folder / 'prepared.json').exists()
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
source = folder / 'test.c'
source.write_text('int linuxcode_original_uba_probe(int a, int b) { return a + b; }\n' +
                  ('int main(void) { return linuxcode_original_uba_probe(40, 2) != 42; }\n'
                   if args.operation == 'link' else ''))
if args.source_file:
    source_input = (root / args.source_file).resolve(strict=True)
    assert source_input.is_relative_to(root)
    source.write_bytes(source_input.read_bytes())
assert not args.response_file or args.operation == 'link'
assert not args.driver_only or args.operation == 'link'
working = (root / args.working_directory).resolve(strict=True) if args.working_directory else folder
assert working.is_relative_to(root)
clang = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang'
sdk = '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk'
uba = root / 'vendor/unreal-engine/Engine/Binaries/Mac/UnrealBuildAccelerator/UbaCli'
clang_args = ['-target', 'arm64-apple-ios15.0', '-isysroot', sdk]
if args.operation == 'compile':
    clang_args.append('-c')
clang_args.append(guest(source))
if args.response_file:
    response = (root / args.response_file).resolve(strict=True)
    assert response.is_relative_to(root)
    clang_args = ['@' + guest(response)]
clang_args += args.extra_argument
if args.driver_only:
    clang_args.append('-###')
suffix = '.o' if args.operation == 'compile' else '.exe'
direct = [clang, *clang_args, '-o', guest(folder / ('direct' + suffix))]
detoured = [guest(uba), '-dir=' + guest(folder / 'storage'), '-workdir=' + guest(working), '-log',
            'local', clang, *clang_args, '-o', guest(folder / ('detoured' + suffix))]
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
profile = runpy.run_path(str(root / 'scripts/native-temporary-runtime-profile.py'))['select'](
    profile, 'artifacts/native-temporary-launcher-v1-stage.json')
if args.compact_library_paths:
    profile = runpy.run_path(str(root / 'scripts/compact-dyld-library-search-paths.py'))['select'](profile)
if args.library_directory:
    directory = (root / args.library_directory).resolve(strict=True)
    assert directory.is_relative_to(root / 'runtime') and directory.is_dir()
    command = list(profile['command'])
    index = next(i for i, value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
    command[index] = 'DYLD_LIBRARY_PATH=' + guest(directory) + ':' + command[index].split('=', 1)[1]
    profile = {**profile, 'command': command}
script = folder / 'run.sh'
snapshot_commands = []
if args.capture_linker_snapshots:
    assert args.operation == 'link'
    for name in ('direct', 'detoured'):
        dest = folder / (name + '-linker-snapshots')
        dest.mkdir()
        snapshot_commands.append('for snapshot in /private/tmp/*.ld-snapshot; do [ -e "$snapshot" ] || continue; cp -R "$snapshot" ' + shlex.quote(guest(dest)) + '/; done\n')
else:
    snapshot_commands = ['', '']
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
                  'cd ' + shlex.quote(guest(working)) + '\n' +
                  shlex.join(direct) + '\nstatus=$?\nprintf "DIRECT_CLANG_STATUS %s\\n" "$status"\n' +
                  snapshot_commands[0] +
                  ('exit "$status"\n' if args.driver_only else
                   ': > ' + shlex.quote(guest(folder / 'local-start')) + '\n' +
                   shlex.join(detoured) + '\nstatus=$?\nprintf "UBA_CLANG_STATUS %s\\n" "$status"\n' +
                   snapshot_commands[1] + 'exit "$status"\n'))
command = profile['command'][:-2] + ['/bin/bash', guest(script)]
command[3] = str(args.timeout_seconds)
env = module['environment'](profile)
for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
    env.pop(name, None)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
(folder / 'prepared.json').write_text(json.dumps(dict(stage=args.stage, operation=args.operation,
    command=command, direct=direct, detoured=detoured,
    compact_library_search_paths=profile.get('compact_library_search_paths', {}).get('report'),
    binary_sha256=sha(uba), source_sha256=sha(source), response_file=args.response_file, response_sha256=sha(response) if args.response_file else None, working_directory=str(working.relative_to(root)), driver_only=args.driver_only, extra_arguments=args.extra_argument, capture_linker_snapshots=args.capture_linker_snapshots, library_directory=args.library_directory), indent=2) + '\n')
print('RUNNING', folder.relative_to(root), flush=True)
log = folder / 'run.log'
with log.open('w') as output:
    result = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
text = log.read_text()
statuses = {name: re.findall(r'^' + name + r'_CLANG_STATUS (\d+)$', text, re.M) for name in ('DIRECT', 'UBA')}
objects = {name: dict(exists=(folder / (name + suffix)).exists()) for name in ('direct', 'detoured')}
for name in objects:
    path = folder / (name + suffix)
    if path.exists():
        objects[name]['sha256'] = sha(path)
        with path.open('rb') as stream:
            header = stream.read(16)
        expected_type = 1 if args.operation == 'compile' else 2
        objects[name]['arm64_macho_expected_type'] = (len(header) == 16 and
            struct.unpack('<4I', header)[:2] == (0xfeedfacf, 0x100000c) and
            struct.unpack('<4I', header)[3] == expected_type)
verified = result.returncode == 0 and statuses == {'DIRECT': ['0'], 'UBA': ['0']} and all(
    row.get('arm64_macho_expected_type', False) for row in objects.values())
if args.driver_only:
    verified = result.returncode == 0 and statuses == {'DIRECT': ['0'], 'UBA': []} and '/usr/bin/ld' in text
report = dict(verified=verified, stage=args.stage, operation=args.operation,
              outer_status=result.returncode, native_statuses=statuses, driver_only=args.driver_only, response_file=args.response_file,
              compact_library_search_paths=profile.get('compact_library_search_paths', {}).get('report'),
              objects=objects, log=str(log.relative_to(root)), log_sha256=sha(log),
              script_sha256=sha(script), probe_source_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(text[-3200:])
print('EVIDENCE', folder / 'result.json', flush=True)
raise SystemExit(0 if verified else 1)
