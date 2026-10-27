#!/usr/bin/env python3
"""Run original Apple Clang directly and through original UBA local execution."""
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
parser.add_argument('--output-dir')
parser.add_argument('--compact-library-paths', action='store_true')
args = parser.parse_args()
folder = (root / args.output_dir).resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix='original-uba-clang-', dir=root / 'runtime'))
assert folder.is_relative_to(root / 'runtime')
folder.mkdir(exist_ok=True)
assert not (folder / 'prepared.json').exists()
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
source = folder / 'test.c'
source.write_text('int linuxcode_original_uba_probe(int a, int b) { return a + b; }\n')
clang = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang'
sdk = '/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk'
uba = root / 'vendor/unreal-engine/Engine/Binaries/Mac/UnrealBuildAccelerator/UbaCli'
clang_args = ['-target', 'arm64-apple-ios15.0', '-isysroot', sdk, '-c', guest(source)]
direct = [clang, *clang_args, '-o', guest(folder / 'direct.o')]
detoured = [guest(uba), '-dir=' + guest(folder / 'storage'), '-workdir=' + guest(folder), '-log',
            'local', clang, *clang_args, '-o', guest(folder / 'detoured.o')]
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
profile = runpy.run_path(str(root / 'scripts/native-temporary-runtime-profile.py'))['select'](
    profile, 'artifacts/native-temporary-launcher-v1-stage.json')
if args.compact_library_paths:
    profile = runpy.run_path(str(root / 'scripts/compact-dyld-library-search-paths.py'))['select'](profile)
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
                  shlex.join(direct) + '\nprintf "DIRECT_CLANG_STATUS %s\\n" "$?"\n' +
                  ': > ' + shlex.quote(guest(folder / 'local-start')) + '\n' +
                  shlex.join(detoured) + '\nstatus=$?\nprintf "UBA_CLANG_STATUS %s\\n" "$status"\nexit "$status"\n')
command = profile['command'][:-2] + ['/bin/bash', guest(script)]
command[3] = '180'
env = module['environment'](profile)
for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
    env.pop(name, None)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
(folder / 'prepared.json').write_text(json.dumps(dict(stage=args.stage, command=command, direct=direct, detoured=detoured,
    compact_library_search_paths=profile.get('compact_library_search_paths', {}).get('report'),
    binary_sha256=sha(uba), source_sha256=sha(source)), indent=2) + '\n')
print('RUNNING', folder.relative_to(root), flush=True)
log = folder / 'run.log'
with log.open('w') as output:
    result = subprocess.run(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
text = log.read_text()
statuses = {name: re.findall(r'^' + name + r'_CLANG_STATUS (\d+)$', text, re.M) for name in ('DIRECT', 'UBA')}
objects = {name: dict(exists=(folder / (name + '.o')).exists()) for name in ('direct', 'detoured')}
for name in objects:
    path = folder / (name + '.o')
    if path.exists():
        objects[name]['sha256'] = sha(path)
verified = result.returncode == 0 and statuses == {'DIRECT': ['0'], 'UBA': ['0']} and all(row['exists'] for row in objects.values())
report = dict(verified=verified, stage=args.stage, outer_status=result.returncode, native_statuses=statuses,
              compact_library_search_paths=profile.get('compact_library_search_paths', {}).get('report'),
              objects=objects, log=str(log.relative_to(root)), log_sha256=sha(log),
              script_sha256=sha(script), probe_source_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(text[-3200:])
print('EVIDENCE', folder / 'result.json', flush=True)
raise SystemExit(0 if verified else 1)
