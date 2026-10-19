#!/usr/bin/env python3
"""Exercise sealed Objective-C selector fixups, dispatch and restored VM protection."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='objc-data-const-test-', dir=root/'runtime'))
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
for name, source in [('plugin', 'fixtures/hello/objc-data-const-plugin.m'),
                     ('probe', 'fixtures/hello/objc-data-const.c')]:
    obj = folder/(name+'.o')
    subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk),
        '-O2', '-c', str(root/source), '-o', str(obj)], check=True)
    subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
        '-syslibroot', str(guest), '-L', str(guest/'usr/lib'), '-L', str(guest/'usr/lib/system'),
        '-lSystem', '-lobjc', *(['-dylib', '-install_name', '/linuxcode-data-const-test.dylib', '-data_const']
                              if name == 'plugin' else []),
        str(obj), '-o', str(folder/name)], check=True)
# Controlled fixture variant: identical metadata, but its data segment stays RW.
payload = bytearray((folder/'plugin').read_bytes())
at = 32
segments = []
for _ in range(struct.unpack_from('<I', payload, 16)[0]):
    command, size = struct.unpack_from('<II', payload, at)
    if command == 0x19 and payload[at+8:at+24].split(b'\0')[0] == b'__DATA_CONST':
        flags = struct.unpack_from('<I', payload, at+68)[0]
        assert flags & 0x10
        segments.append(dict(flags=flags, vmaddr=struct.unpack_from('<Q', payload, at+24)[0]))
        struct.pack_into('<I', payload, at+68, flags & ~0x10)
    at += size
assert len(segments) == 1
(folder/'writable-plugin').write_bytes(payload)
configuration = json.loads((root/args.configuration).read_text())
assert configuration.get('objc_source_build')
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
cases = []
for mode in ['old-readonly', 'new-readonly', 'new-writable']:
    selected = dict(configuration)
    if mode == 'old-readonly':
        selected.pop('objc_source_build')
        selected.pop('objc_source_build_sha256')
    path = folder/(mode+'.json')
    path.write_text(json.dumps(selected, indent=2)+'\n')
    p = module['profile'](stage=args.stage, configuration=str(path.relative_to(root)))
    plugin = folder/('writable-plugin' if mode == 'new-writable' else 'plugin')
    argv = ['/Volumes/SystemRoot/workspace/'+str((folder/'probe').relative_to(root)),
            '/Volumes/SystemRoot/workspace/'+str(plugin.relative_to(root)),
            'writable' if mode == 'new-writable' else 'readonly']
    script = folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\n'+shlex.join(argv)+
                     '\nstatus=$?\nprintf "OBJC_CONST_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = p['command'][:-2]+['/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
    command[3] = '60'
    log = folder/(mode+'.log')
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=root, env=module['environment'](p), stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text()
    statuses = re.findall(r'^OBJC_CONST_STATUS (\d+)$', text, re.M)
    marker = 'OBJC_DATA_CONST_SELECTOR_IDENTITY_DISPATCH_PROTECTION_OK'
    verified = ((result.returncode == 139 and statuses == ['139'] and marker not in text)
                if mode == 'old-readonly' else
                (result.returncode == 0 and statuses == ['0'] and marker in text))
    cases.append(dict(mode=mode, verified=verified, outer_status=result.returncode,
        native_status=statuses, command=command, log=str(log.relative_to(root)),
        log_sha256=sha(log.relative_to(root))))
    print(mode, verified, text[-1000:], flush=True)
record = dict(verified=all(row['verified'] for row in cases), cases=cases,
    configuration=args.configuration, configuration_sha256=sha(args.configuration), stage=args.stage,
    fixture_segments=segments, sources={name: sha(name) for name in [
        'scripts/probe-objc-data-const.py', 'fixtures/hello/objc-data-const-plugin.m',
        'fixtures/hello/objc-data-const.c']}, full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
