#!/usr/bin/env python3
"""Exercise Intel ARC claim semantics in the actual complete objc4 candidate."""
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
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage', required=True)
p.add_argument('--configuration', required=True)
p.add_argument('--baseline-configuration', required=True)
p.add_argument('--prepare-only', action='store_true')
a = p.parse_args()
folder = Path(tempfile.mkdtemp(prefix='objc-claim-return-', dir=root / 'runtime'))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
config = json.loads((root / a.configuration).read_text())
build = json.loads((root / config['objc_source_build']).read_text())
assert build['full_objc_source_build'] and build['complete_source_files'] == 43
provider = build['library']
sdk = root / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
old_headers = root / 'vendor/darling/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/usr/include'
source = root / 'fixtures/hello/objc-claim-return.m'
obj, binary = folder / 'probe.o', folder / 'probe'
commands = [
    ['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
        '-I' + str((root / provider).parent / 'include'), '-I' + str(old_headers),
        '-fno-objc-arc', '-O2', '-c', str(source), '-o', str(obj)],
    ['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
        '-syslibroot', str(sdk), '-lobjc', '-lSystem', '-no_fixup_chains',
        '-no_adhoc_codesign', str(obj), '-o', str(binary)],
]
with (folder / 'compile.log').open('w') as out:
    for command in commands:
        subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT, check=True)
disassembly = subprocess.check_output(['llvm-objdump-19', '--macho', '--disassemble', str(binary)], text=True)
(folder / 'disassembly.txt').write_text(disassembly)
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))
cases = []
for mode, configuration in [('missing', a.baseline_configuration), ('candidate', a.configuration)]:
    profile = module['profile'](stage=a.stage, configuration=configuration)
    command = list(profile['command'][:-2])
    for key in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']:
        index = next(i for i, value in enumerate(command) if value.startswith(key + '='))
        command[index] = key + '=' + profile['direct_resource_environment']['tool_environment'][key]
    script = folder / (mode + '.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
        shlex.join([guest(binary), '/' + provider, mode]) +
        '\nstatus=$?\nprintf "OBJC_CLAIM_STATUS %s\\n" "$status"\nexit "$status"\n')
    command += ['/bin/bash', guest(script)]
    command[3] = '45'
    row = dict(mode=mode, configuration=configuration, command=command,
        runtime_execution_attempted=not a.prepare_only, verified=False)
    if not a.prepare_only:
        log = folder / (mode + '.log')
        with log.open('w') as out:
            result = subprocess.run(command, cwd=root, env=module['environment'](profile), stdout=out, stderr=subprocess.STDOUT)
        text = log.read_text()
        marker = 'OBJC_CLAIM_BASELINE_API_MISSING_OK' if mode == 'missing' else 'OBJC_CLAIM_RETURN_NATIVE_OK'
        row.update(status=result.returncode, verified=result.returncode == 0 and marker in text and 'OBJC_CLAIM_STATUS 0' in text,
            log=str(log.relative_to(root)), log_sha256=sha(log), checks=re.findall(r'checks=(\d+)', text))
        print(mode, result.returncode, text[-3000:], flush=True)
    cases.append(row)
    if not a.prepare_only and not row['verified']:
        break
record = dict(prepared=True, verified=not a.prepare_only and len(cases) == 2 and all(row['verified'] for row in cases),
    stage=a.stage, build=config['objc_source_build'], build_sha256=sha(root / config['objc_source_build']),
    provider=provider, provider_sha256=sha(root / provider), build_commands=commands,
    source=str(source.relative_to(root)), source_sha256=sha(source), driver_sha256=sha(Path(__file__)),
    disassembly=str((folder / 'disassembly.txt').relative_to(root)), cases=cases,
    tls_test='Seed the actual reserved upstream pthread TSD slot for isolated +1 consumption/clearing; no ARC function is mocked or replaced. A separate actual producer/callsite test verifies the unrecognized claim fallback and object lifetime.',
    native_execution_attempted=not a.prepare_only, full_Unity_execution_verified=False)
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder / 'result.json')
raise SystemExit(0 if a.prepare_only or record['verified'] else 1)
