#!/usr/bin/env python3
"""Reproduce a held kernel-kqueue mutex across a real multithreaded fork."""
from pathlib import Path
import argparse, hashlib, json, re, runpy, shlex, struct, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
parser.add_argument('--expect-child-timeout', action='store_true')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='fork-kqueue-redirect-', dir=root / 'runtime'))
stage = json.loads((root / args.stage).read_text())
kernel = root / stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']
symbols = subprocess.check_output(['llvm-nm-19', '--defined-only', str(kernel)], text=True)
matches = re.findall(r'^([\da-fA-F]+)\s+\S\s+_kq_mtx$', symbols, re.M); assert len(matches) == 1
data = kernel.read_bytes(); cursor = 32; text_base = None
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    kind, size = struct.unpack_from('<II', data, cursor)
    if kind == 0x19 and data[cursor + 8:cursor + 24].split(b'\0')[0] == b'__TEXT': text_base = struct.unpack_from('<Q', data, cursor + 24)[0]
    cursor += size
assert text_base is not None
lock_offset = int(matches[0], 16) - text_base
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = root / 'fixtures/hello/fork-kqueue-redirect.c'
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
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' + shlex.join([guest(folder / 'test'), format(lock_offset, 'x'), 'negative' if args.expect_child_timeout else 'positive']) +
                  '\ns=$?\nprintf "FORK_KQUEUE_STATUS %s\\n" "$s"\nexit "$s"\n')
command = command[:-2] + ['/bin/bash', guest(script)]; command[3] = '65'
log = folder / 'run.log'; print('RUNNING', folder.relative_to(root), flush=True)
with log.open('w') as stream: result = subprocess.run(command, cwd=root, env=module['environment'](profile), stdout=stream, stderr=subprocess.STDOUT)
output = log.read_text()
marker = 'FORK_KQUEUE_OLD_MUTEX_DEADLOCK_REPRODUCED' if args.expect_child_timeout else 'FORK_KQUEUE_CHILD_USER_HANDLER_REDIRECT_NEW_QUEUE_AND_PARENT_READINESS_OK'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
record = dict(verified=result.returncode == 0 and marker in output and 'FORK_KQUEUE_STATUS 0' in output,
              stage=args.stage, configuration=args.configuration, expected_child_timeout=args.expect_child_timeout,
              deliberate_fault_injection='A separate real thread owns the selected kernel image kq_mtx during fork; no kernel instructions are patched',
              private_mutex_offset=lock_offset, kernel_sha256=sha(kernel), command=command, commands=commands,
              outer_status=result.returncode, log=str(log.relative_to(root)), log_sha256=sha(log),
              source_sha256=sha(source), driver_sha256=sha(Path(__file__)), full_goal_complete=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n'); print(output[-2400:]); print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if record['verified'] else 1)
