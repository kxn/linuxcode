#!/usr/bin/env python3
"""Check the actual libSystem reexport and rich-error objects in the resource scope."""
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
parser.add_argument('--configuration', required=True)
parser.add_argument('--control-configuration', required=True)
parser.add_argument('--control-stage')
parser.add_argument('--provider', default='runtime/native-library-stage/libDarlingXPCRichError.dylib')
parser.add_argument('--check-normal-runtime', action='store_true')
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='resource-system-peer-test-', dir=root/'runtime'))
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
objects = []
for source, options in [('fixtures/hello/xpc-rich-error.c', ['-Dmain=rich_error_existing_probe_main']),
                        ('fixtures/hello/resource-system-peer-error.c', [])]:
    obj = folder/(Path(source).stem+'.o')
    subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
                    '-fblocks', *options, '-c', str(root/source), '-o', str(obj)], check=True)
    objects.append(str(obj))
binary = folder/'peer-error'
subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-syslibroot', str(guest), '-L', str(guest/'usr/lib'), '-L', str(guest/'usr/lib/system'),
    '-lSystem', '-lxpc', *objects, '-o', str(binary)], check=True)
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
provider = args.provider
guest_binary = '/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))
cases = []
selections = [
    ('missing', args.control_configuration, 'RESOURCE_SYSTEM_PEER_ERROR_ABSENT_CONTROL_OK'),
    ('present', args.configuration, 'RESOURCE_SYSTEM_PEER_ERROR_REEXPORT_IDENTITY_AND_REAL_OBJECTS_OK')]
if args.check_normal_runtime:
    selections.append(('normal', args.configuration, 'RESOURCE_SYSTEM_PEER_ERROR_REEXPORT_IDENTITY_AND_REAL_OBJECTS_OK'))
for mode, configuration, marker in selections:
    config = json.loads((root/configuration).read_text())
    config['executables'] = [*config['executables'], guest_binary]
    selected = folder/(mode+'-configuration.json')
    selected.write_text(json.dumps(config, indent=2)+'\n')
    print('SELECTING', mode, configuration, flush=True)
    selected_stage = args.control_stage if mode == 'missing' and args.control_stage else args.stage
    selected_module = (runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
                       if mode == 'normal' else module)
    p = (selected_module['profile'](stage=selected_stage) if mode == 'normal' else
         module['profile'](stage=selected_stage, configuration=str(selected.relative_to(root))))
    selected_provider = (json.loads((root/args.stage).read_text())['peer_error_adapter']['path']
                         if mode == 'normal' else provider)
    script = folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join([guest_binary, '/Volumes/SystemRoot/workspace/'+selected_provider,
                    'present' if mode == 'normal' else mode])+
        '\nstatus=$?\nprintf "RESOURCE_PEER_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = p['command'][:-2]+['/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
    command[3] = '90'
    environment = selected_module['environment'](p)
    for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
        environment.pop(name, None)
    log = folder/(mode+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^RESOURCE_PEER_STATUS (\d+)$', text, re.M)
    verified = result.returncode == 0 and statuses == ['0'] and marker in text
    if mode in ('present', 'normal'):
        verified = verified and 'XPC_RICH_ERROR_ACTUAL_OBJECTS_COPY_RETRY_RETAIN_AND_PEER_ERROR_OK' in text
    cases.append(dict(mode=mode, configuration=configuration, stage=selected_stage, command=command,
        configuration_applied=mode != 'normal', selected_provider=selected_provider,
        configuration_sha256=sha(configuration), log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)),
        outer_status=result.returncode, native_status=statuses, verified=verified))
    print(mode, text[-1800:], flush=True)
record = dict(verified=all(case['verified'] for case in cases), cases=cases, stage=args.stage,
    sources={name: sha(name) for name in ['scripts/probe-resource-system-peer-error.py',
        'fixtures/hello/xpc-rich-error.c', 'fixtures/hello/resource-system-peer-error.c']},
    provider_sha256=sha(provider), real_rich_error_cases=160,
    normal_runtime_verified=any(case['mode'] == 'normal' and case['verified'] for case in cases),
    peer_signing_enforcement_added=False)
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
