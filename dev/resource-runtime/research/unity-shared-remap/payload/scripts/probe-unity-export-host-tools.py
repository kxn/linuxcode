#!/usr/bin/env python3
"""Run the unmodified macOS x86_64 tools in a pinned Unity export on Darling.

This is a host-tool startup probe, never evidence of a completed iOS build.
Both exports contain unmodified macOS tools, regardless of the iOS target.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-profile', default='scripts/xcode-tool-dispatch-runtime-profile.py')
parser.add_argument('--export', choices=['simulator', 'device'], default='simulator')
parser.add_argument('--runtime-stage', help='Explicit stage for a profile that accepts stage=')
parser.add_argument('--timeout-seconds', type=int, default=90)
args = parser.parse_args()
assert 1 <= args.timeout_seconds <= 86400
if args.export == 'simulator':
    source = root / 'runtime/unity-quick-actions-export'
    commit = 'a2a2f5f1883b14358693a0f3a3a4372b24aab7d8'
    repository = 'https://github.com/SuQiang2007/iOSHomeQuickActionsOCWrapper'
    project = source
    target = 'iOS Simulator x86_64'
else:
    source = root / 'runtime/unity-uemuera-device-export'
    commit = '3944888ac3917624081ff18beca2874c0ec19748'
    repository = 'https://github.com/kusadact/uEmuera-for-iOS'
    project = source / 'ios'
    target = 'iPhoneOS arm64'
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == commit
# Unity's own PBX shell phase chmods its bundled tools. Permit that expected
# mode change, but continue to reject any tracked content/index modification.
assert not subprocess.check_output(['git', '-c', 'core.filemode=false', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
mode_changes = subprocess.check_output(['git', '-C', str(source), 'diff', '--summary'], text=True).splitlines()
folder = Path(tempfile.mkdtemp(prefix='unity-export-host-tools-', dir=root / 'runtime'))
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
deploy = project / 'Il2CppOutputProject/IL2CPP/build/deploy_x86_64'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z'], text=True).split('\0')
inputs = {str((source / name).relative_to(root)): sha(source / name) for name in tracked if name}
(folder / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
module = runpy.run_path(str(root / args.runtime_profile))
p = module['profile'](**({'stage': args.runtime_stage} if args.runtime_stage else {}))
env = module['environment'](p)
gui = ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY')
for name in gui:
    env.pop(name, None)
cases = []
for name, tool in [('il2cpp', deploy / 'il2cpp'), ('bee', deploy / 'bee_backend/mac-x64/bee_backend')]:
    script = folder / (name + '.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\ncd ' + shlex.quote(guest(folder)) + '\n' +
        shlex.join([guest(tool), '--help']) + '\nstatus=$?\n' +
        'printf "UNITY_HOST_TOOL_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = p['command'][:-2] + ['/usr/bin/env',
        *[arg for name in gui for arg in ('-u', name)], '/bin/bash', guest(script)]
    command[3] = str(args.timeout_seconds)
    log = folder / (name + '.log')
    started = time.monotonic()
    with log.open('w') as stream:
        result = subprocess.run(command, env=env, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - started
    text = log.read_text()
    statuses = re.findall(r'^UNITY_HOST_TOOL_STATUS (\d+)$', text, re.M)
    case = dict(name=name, elapsed_seconds=elapsed, timeout_seconds=args.timeout_seconds,
        tool=str(tool.relative_to(root)), tool_sha256=sha(tool),
        command=command, outer_status=result.returncode, native_status=statuses,
        log=str(log.relative_to(root)), log_sha256=sha(log),
        native_exit_zero=result.returncode == 0 and statuses == ['0'])
    cases.append(case)
    print(name, 'outer_status', result.returncode, 'native_status', statuses, '\n', text[-4000:], flush=True)
record = dict(repository=repository, commit=commit, original_export_modified=False,
    original_export_bytes_modified=False, original_export_mode_changes=mode_changes,
    runtime_profile=args.runtime_profile, runtime_profile_sha256=sha(root / args.runtime_profile),
    runtime_stage=args.runtime_stage, runtime_stage_sha256=sha(root / args.runtime_stage) if args.runtime_stage else None,
    export_target=target, inputs=str((folder / 'inputs.json').relative_to(root)),
    inputs_sha256=sha(folder / 'inputs.json'), gui_environment_removed=list(gui),
    cases=cases, host_tool_exit_checks_passed=all(c['native_exit_zero'] for c in cases),
    iPhoneOS_build_verified=False, engine_build_verified=False, signing_verified=False,
    files={str(path.relative_to(root)): sha(path) for path in [Path(__file__), *folder.glob('*.sh')]})
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json', flush=True)
raise SystemExit(0 if record['host_tool_exit_checks_passed'] else 1)
