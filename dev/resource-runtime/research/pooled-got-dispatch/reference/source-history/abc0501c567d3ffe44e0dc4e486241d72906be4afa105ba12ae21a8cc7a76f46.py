#!/usr/bin/env python3
"""Check the source type, original scalar ABI and real workloop regression.

No exclaves event capability is claimed. The unchanged Linux backend must reject
that filter, while source allocation/cancellation uses genuine libdispatch code.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True)
parser.add_argument('--stage', required=True)
parser.add_argument('--system-build', required=True)
args = parser.parse_args()
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
dispatch = json.loads((root/args.build).read_text())
system = json.loads((root/args.system_build).read_text())
assert dispatch['full_libdispatch_source_build'] and dispatch['complete_source_files'] == 32
assert sha(dispatch['library']) == dispatch['library_sha256']
assert sha(system['output']) == system['output_sha256']
folder = Path(tempfile.mkdtemp(prefix='dispatch-exclaves-type-', dir=root/'runtime'))
compile_command = list(next(row['command'] for row in dispatch['sources'] if row['source'].endswith('/event_kevent.c')))
original_index = compile_command.index('-c')
for name, source in [('type', 'fixtures/hello/dispatch-exclaves-type.c'),
                     ('workloop', 'fixtures/hello/dispatch-workloop-context.c')]:
    obj = folder/(name+'.o')
    command = compile_command[:original_index]+['-c', str(root/source), '-o', str(obj)]
    subprocess.run(command, cwd=root, check=True)
    subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
        '-syslibroot', str(root/'runtime/rootfs/usr/libexec/darling'), '-lSystem', str(obj),
        '-o', str(folder/name)], cwd=root, check=True)
module = runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p = module['profile'](stage=args.stage)
environment = module['environment'](p)
for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    environment.pop(key, None)
guest = lambda path: '/Volumes/SystemRoot/workspace/'+str(path)
cases = []
for label, program, mode in [('missing', 'type', 'missing'), ('present', 'type', 'present'),
                             ('workloop', 'workloop', '')]:
    script = folder/(label+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        guest((folder/program).relative_to(root))+' '+mode+'\nstatus=$?\n'+
        'printf "DISPATCH_TYPE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = list(p['command'][:-2])
    index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
    paths = [str(Path(system['output']).parent)]
    if label != 'missing':
        paths.insert(0, str(Path(dispatch['library']).parent))
    command[index] = 'DYLD_LIBRARY_PATH='+':'.join(guest(path) for path in paths)+':'+command[index].split('=', 1)[1]
    command += ['/bin/bash', guest(script.relative_to(root))]
    command[3] = '120'
    log = folder/(label+'.log')
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
    text = log.read_text()
    markers = {'missing': 'DISPATCH_EXCLAVES_TYPE_ABSENT_CONTROL_OK',
        'present': 'DISPATCH_EXCLAVES_TYPE_LAYOUT_CALLBACKS_CANCEL_AND_ASYNC_OK',
        'workloop': 'WORKLOOP_REAL_NESTED_TARGET_FIFO_SYNC_RESTORE_AND_INDEPENDENT_ROOT_CONTEXT_OK'}
    statuses = re.findall(r'^DISPATCH_TYPE_STATUS (\d+)$', text, re.M)
    verified = result.returncode == 0 and statuses == ['0'] and markers[label] in text
    cases.append(dict(mode=label, verified=verified, outer_status=result.returncode,
        native_status=statuses, log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)), command=command))
    print(label, result.returncode, text[-1800:], flush=True)
    if not verified:
        break
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
image = '/usr/lib/system/libdispatch.dylib'
address = ns['resolve'](image, '__dispatch_source_type_exclaves_notification')
data = ns['read'](address, 32)
original = dict(kind=ns['read'](ns['pointer'](address), 64).split(b'\0')[0].decode(),
    filter=struct.unpack_from('<b', data, 8)[0], action=data[9], flags=struct.unpack_from('<H', data, 12)[0],
    fflags=struct.unpack_from('<I', data, 16)[0], mask=struct.unpack_from('<I', data, 20)[0],
    size=struct.unpack_from('<I', data, 24)[0])
positive = next((case for case in cases if case['mode'] == 'present'), None)
scalar_match = False
if positive and positive['verified']:
    text = (root/positive['log']).read_text()
    layout = re.search(r'^DISPATCH_EXCLAVES_LAYOUT (.+)$', text, re.M)
    actual = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', layout[1])}
    scalar_match = all(actual[key] == original[key] for key in ['filter', 'action', 'flags', 'fflags', 'mask'])
    for field in ['OWNER', 'CREATE_OWNER', 'MERGE_OWNER']:
        owner = re.search(r'^DISPATCH_EXCLAVES_'+field+r' (.+)$', text, re.M)
        assert owner and owner[1].endswith(dispatch['library'])
    assert 'DISPATCH_EXCLAVES_UNSUPPORTED_FILTER error=' in text
verified = len(cases) == 3 and all(case['verified'] for case in cases) and scalar_match
report = dict(verified=verified, build=args.build, build_sha256=sha(args.build),
    dispatch_library=dispatch['library'], dispatch_library_sha256=sha(dispatch['library']),
    system_build=args.system_build, stage=args.stage, cases=cases,
    original_type_scalar_fields=original, scalar_ABI_match=scalar_match,
    backend_filter_rejected=bool(positive and positive['verified']),
    exclaves_event_delivery_verified=False, full_resource_compilation_verified=False,
    sources={path: sha(path) for path in ['scripts/probe-dispatch-exclaves-type.py',
        'fixtures/hello/dispatch-exclaves-type.c', 'fixtures/hello/dispatch-workloop-context.c']})
(folder/'result.json').write_text(json.dumps(report, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if verified else 1)
