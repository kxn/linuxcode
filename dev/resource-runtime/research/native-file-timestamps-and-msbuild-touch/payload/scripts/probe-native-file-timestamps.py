#!/usr/bin/env python3
"""Reproduce a held kernel-kqueue mutex across a real multithreaded fork."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shlex, struct, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--expect-failures', action='store_true')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='native-file-timestamps-', dir=root / 'runtime'))
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = root / 'fixtures/hello/native-file-timestamps.c'
commands = [['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-std=gnu11', '-O1', '-c', str(source), '-o', str(folder / 'test.o')],
            ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(sdk), '-lSystem', str(folder / 'test.o'), '-o', str(folder / 'test')]]
for command in commands: subprocess.run(command, check=True)
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
command = list(profile['command']); scope = profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
    index = next(i for i, value in enumerate(command) if value.startswith(key + '=')); command[index] = key + '=' + scope[key]
guest = lambda p: '/Volumes/SystemRoot/workspace/' + str(p.relative_to(root))
script = folder / 'run.sh'
native = root / 'runtime/unreal-dotnet-mac-x64-v1/Engine/Binaries/ThirdParty/DotNet/10.0/mac-x64/shared/Microsoft.NETCore.App/10.0.7/libSystem.Native.dylib'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' + shlex.join([guest(folder / 'test'), guest(folder), guest(native)]) + '\ns=$?\nprintf "TIMESTAMP_STATUS %s\\n" "$s"\nexit "$s"\n')
command = command[:-2] + ['/bin/bash', guest(script)]; command[3] = '65'
log = folder / 'run.log'; print('RUNNING', folder.relative_to(root), flush=True)
with log.open('w') as stream: result = subprocess.run(command, cwd=root, env=module['environment'](profile), stdout=stream, stderr=subprocess.STDOUT)
output = log.read_text()
failures = int(re.search(r'^TIMESTAMP_FAILURES (\d+)$', output, re.M)[1]) if re.search(r'^TIMESTAMP_FAILURES (\d+)$', output, re.M) else None
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
record = dict(verified=result.returncode == 0 and failures is not None and (failures > 0 if args.expect_failures else failures == 0),
              all_timestamp_cases_passed=failures == 0, failures=failures, expected_failure=args.expect_failures,
              stage=args.stage, configuration=args.configuration, command=command, commands=commands,
              outer_status=result.returncode, log=str(log.relative_to(root)), log_sha256=sha(log),
              source_sha256=sha(source), driver_sha256=sha(Path(__file__)), original_dotnet_native_sha256=sha(native), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n'); print(output[-3000:]); print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if record['verified'] else 1)
