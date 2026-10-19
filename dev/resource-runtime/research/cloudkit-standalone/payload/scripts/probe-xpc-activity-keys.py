#!/usr/bin/env python3
"""Compare actual backend keys with pinned original data and real XPC criteria."""
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
parser.add_argument('--reference', required=True)
parser.add_argument('--stage', required=True)
parser.add_argument('--control-stage', required=True)
args = parser.parse_args()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
reference = json.loads((root/args.reference).read_text())
assert sha('runtime/fullsystem-libraries'+reference['original_image']) == reference['original_image_sha256']
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
for row in reference['rows']:
    address = ns['resolve'](reference['original_image'], row['symbol'])
    assert address == int(row['address'], 16)
    pointer = ns['pointer'](address)
    assert pointer == int(row['cstring_address'], 16)
    assert ns['read'](pointer, len(row['value'])+1) == row['value'].encode()+b'\0'
assert sum(not row['already_exported'] for row in reference['rows']) == 1
folder = Path(tempfile.mkdtemp(prefix='xpc-activity-keys-', dir=root/'runtime'))
header = 'struct ActivityKey { const char *symbol, *value; bool added; };\nstatic const struct ActivityKey activity_keys[]={\n'
for row in reference['rows']:
    header += '{'+json.dumps(row['symbol'][1:])+','+json.dumps(row['value'])+','+str(not row['already_exported']).lower()+'},\n'
(folder/'activity-keys.h').write_text(header+'};\n')
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
obj, binary = folder/'keys.o', folder/'keys'
subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
    '-I', str(folder), '-c', str(root/'fixtures/hello/xpc-activity-keys.c'), '-o', str(obj)], check=True)
subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-syslibroot', str(guest), '-L', str(guest/'usr/lib'), '-L', str(guest/'usr/lib/system'),
    '-lSystem', '-lxpc', str(obj), '-o', str(binary)], check=True)
module = runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
cases = []
for mode, stage in [('missing', args.control_stage), ('present', args.stage)]:
    print('SELECTING', mode, stage, flush=True)
    p = module['profile'](stage=stage)
    script = folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join(['/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root)), mode])+
        '\nstatus=$?\nprintf "XPC_ACTIVITY_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = p['command'][:-2]+['/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
    command[3] = '60'
    environment = module['environment'](p)
    for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
        environment.pop(name, None)
    log = folder/(mode+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^XPC_ACTIVITY_STATUS (\d+)$', text, re.M)
    marker = ('XPC_ACTIVITY_UPLOAD_KEY_ABSENT_CONTROL_OK' if mode == 'missing' else
              'XPC_ACTIVITY_KEYS_AND_CRITERIA_OK keys='+str(len(reference['rows']))+' values='+str(3*len(reference['rows'])))
    cases.append(dict(mode=mode, stage=stage, verified=result.returncode == 0 and statuses == ['0'] and marker in text,
        command=command, log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)),
        outer_status=result.returncode, native_status=statuses))
    print(mode, text[-1500:], flush=True)
report = dict(verified=all(case['verified'] for case in cases), cases=cases,
    original_data_reference=args.reference, reference_sha256=sha(args.reference),
    actual_key_values=len(reference['rows']), positive_criteria_values=3*len(reference['rows']),
    activity_scheduling_implemented=False,
    sources={name: sha(name) for name in ['scripts/probe-xpc-activity-keys.py', 'fixtures/hello/xpc-activity-keys.c']})
(folder/'result.json').write_text(json.dumps(report, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if report['verified'] else 1)
