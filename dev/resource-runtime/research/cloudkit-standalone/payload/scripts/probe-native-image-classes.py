#!/usr/bin/env python3
"""Load one real image and inspect selected original classes in the resource scope."""
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
parser.add_argument('--image', required=True)
parser.add_argument('--class-name', action='append', required=True)
parser.add_argument('--stage', required=True)
parser.add_argument('--configuration', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='native-image-classes-', dir=root/'runtime'))
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
before = sha(args.image)
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
obj = folder/'probe.o'
binary = folder/'probe'
subprocess.run(['clang-19', '-target', 'x86_64-apple-macos11', '-isysroot', str(sdk), '-c',
    str(root/'fixtures/hello/native-image-classes.c'), '-o', str(obj)], check=True)
subprocess.run(['ld64.lld-19', '-arch', 'x86_64', '-platform_version', 'macos', '11', '11',
    '-syslibroot', str(guest), '-L', str(guest/'usr/lib'), '-L', str(guest/'usr/lib/system'),
    '-lSystem', '-lobjc', str(obj), '-o', str(binary)], check=True)
guest_binary = '/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))
configuration = json.loads((root/args.configuration).read_text())
configuration['executables'].append(guest_binary)
selected = folder/'configuration.json'
selected.write_text(json.dumps(configuration, indent=2)+'\n')
module = runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
p = module['profile'](stage=args.stage, configuration=str(selected.relative_to(root)))
script = folder/'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
    shlex.join([guest_binary, '/Volumes/SystemRoot/workspace/'+args.image, *args.class_name])+
    '\nstatus=$?\nprintf "NATIVE_IMAGE_STATUS %s\\n" "$status"\nexit "$status"\n')
command = p['command'][:-2]+['/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
command[3] = '90'
environment = module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    environment.pop(name, None)
log = folder/'run.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
text = log.read_text()
statuses = re.findall(r'^NATIVE_IMAGE_STATUS (\d+)$', text, re.M)
marker = 'NATIVE_IMAGE_CLASS_LOAD_OK classes='+str(len(args.class_name))
assert sha(args.image) == before
record = dict(verified=result.returncode == 0 and statuses == ['0'] and marker in text,
    image=args.image, image_sha256=before, rtld_lazy=True, classes=args.class_name,
    stage=args.stage, configuration=args.configuration, command=command,
    log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)),
    outer_status=result.returncode, native_status=statuses, full_API_semantics_verified=False,
    sources={name: sha(name) for name in ['scripts/probe-native-image-classes.py',
                                        'fixtures/hello/native-image-classes.c']})
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text[-3000:])
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
