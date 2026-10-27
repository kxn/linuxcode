#!/usr/bin/env python3
"""Verify the private resolver binding and real Darwin getaddrinfo calls."""
from pathlib import Path
import argparse, hashlib, json, runpy, shlex, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--temporary-stage', required=True)
parser.add_argument('--resolver-stage', required=True)
parser.add_argument('--configuration', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='private-native-resolver-', dir=root / 'runtime'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
guest = lambda p: '/Volumes/SystemRoot/workspace/' + str(p.relative_to(root))
source = root / 'fixtures/hello/private-native-resolver.c'
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-O1', '-c', str(source), '-o', str(folder / 'test.o')],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11', '-syslibroot', str(sdk), '-lSystem', str(folder / 'test.o'), '-o', str(folder / 'test')]]
for command in commands: subprocess.run(command, check=True)
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
profile = module['profile'](stage=args.stage, configuration=args.configuration)
profile = runpy.run_path(str(root / 'scripts/native-temporary-runtime-profile.py'))['select'](profile, args.temporary_stage)
profile = runpy.run_path(str(root / 'scripts/native-resolver-runtime-profile.py'))['select'](profile, args.resolver_stage)
stage = json.loads((root / args.resolver_stage).read_text())
guards = [Path('/etc/resolv.conf'), root / 'runtime/rootfs/usr/libexec/darling/private/etc/resolv.conf']
before = {str(p): sha(p) for p in guards}
script = folder / 'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' + shlex.join([guest(folder / 'test'), guest(root / stage['resolver_snapshot'])]) + '\ns=$?\nprintf "PRIVATE_RESOLVER_STATUS %s\\n" "$s"\nexit "$s"\n')
command = profile['command'][:-2] + ['/bin/bash', guest(script)]; command[3] = '65'
print('RUNNING', folder.relative_to(root), flush=True)
log = folder / 'run.log'
with log.open('w') as stream: result = subprocess.run(command, cwd=root, env=module['environment'](profile), stdout=stream, stderr=subprocess.STDOUT)
text = log.read_text(); preserved = all(sha(Path(p)) == h for p, h in before.items())
verified = result.returncode == 0 and 'PRIVATE_NATIVE_RESOLVER_REAL_LOOKUPS_OK' in text and 'PRIVATE_RESOLVER_STATUS 0' in text and preserved
record = dict(verified=verified, outer_status=result.returncode, command=command, commands=commands,
              stage=args.stage, resolver_stage=args.resolver_stage, temporary_stage=args.temporary_stage,
              configuration=args.configuration, host_and_backing_resolver_preserved=preserved,
              log=str(log.relative_to(root)), log_sha256=sha(log), source_sha256=sha(source),
              driver_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print(text[-2000:]); print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if verified else 1)
