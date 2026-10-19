#!/usr/bin/env python3
"""Check the actual CFString facade/leaf identity and ordinary CF operations."""
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
parser.add_argument('--overlay', required=True)
parser.add_argument('--reference', required=True)
args = parser.parse_args()
sha = lambda name: hashlib.sha256((root/name).read_bytes()).hexdigest()
overlay = json.loads((root/args.overlay).read_text())
reference = json.loads((root/args.reference).read_text())
assert overlay['identifier_only'] and not overlay['sharing_operations_implemented']
resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name, digest in overlay['files'].items():
    resolve(name, digest)
folder = Path(tempfile.mkdtemp(prefix='security-sharing-identifier-', dir=root/'runtime'))
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
obj, binary = folder/'probe.o', folder/'probe'
subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
    '-c', str(root/'fixtures/hello/security-sharing-group-constant.c'), '-o', str(obj)], check=True)
subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-syslibroot', str(guest), '-L', str(guest/'usr/lib'), '-L', str(guest/'usr/lib/system'),
    '-lSystem', '-framework', 'CoreFoundation', str(obj), '-o', str(binary)], check=True)
module = runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
cases = []
for mode in ['missing', 'present']:
    print('SELECTING', mode, flush=True)
    p = module['profile'](stage=args.stage)
    command = list(p['command'])
    if mode == 'present':
        for variable, field in [('DYLD_FRAMEWORK_PATH', 'frameworks'), ('DYLD_LIBRARY_PATH', 'libraries')]:
            index = next(i for i, item in enumerate(command) if item.startswith(variable+'='))
            command[index] = variable+'=/Volumes/SystemRoot/workspace/'+overlay[field]+':'+command[index].split('=', 1)[1]
    script = folder/(mode+'.sh')
    provider = overlay['libraries']+'/libDarlingSecurityResourceConstants.dylib'
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join(['/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root)),
            '/Volumes/SystemRoot/workspace/'+provider, reference['value'], mode])+
        '\nstatus=$?\nprintf "SHARING_IDENTIFIER_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = command[:-2]+['/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
    command[3] = '60'
    environment = module['environment'](p)
    for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
        environment.pop(name, None)
    log = folder/(mode+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^SHARING_IDENTIFIER_STATUS (\d+)$', text, re.M)
    marker = ('SECURITY_SHARING_IDENTIFIER_ABSENT_CONTROL_OK' if mode == 'missing' else
              'SECURITY_SHARING_IDENTIFIER_TYPE_VALUE_COPY_DICTIONARY_OK')
    cases.append(dict(mode=mode, verified=result.returncode == 0 and statuses == ['0'] and marker in text,
        command=command, outer_status=result.returncode, native_status=statuses,
        log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root))))
    print(mode, text[-1600:], flush=True)
record = dict(verified=all(case['verified'] for case in cases), cases=cases, stage=args.stage,
    overlay=args.overlay, overlay_sha256=sha(args.overlay), reference=args.reference,
    reference_sha256=sha(args.reference), sharing_operations_implemented=False,
    sources={name: sha(name) for name in ['scripts/probe-security-resource-constant.py',
        'fixtures/hello/security-sharing-group-constant.c']})
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
