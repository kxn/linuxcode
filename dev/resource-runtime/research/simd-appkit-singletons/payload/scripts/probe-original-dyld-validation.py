#!/usr/bin/env python3
"""Validate a rebuilt image and damaged controls with unmodified Apple dyld_info."""
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
parser.add_argument('--image', required=True)
parser.add_argument('--reference-image', required=True)
parser.add_argument('--stage', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-dyld-validation-', dir=root/'runtime'))
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
image = (root/args.image).read_bytes()


def commands(data):
    assert data[:8] == bytes.fromhex('cffaedfe07000001')
    at = 32
    result = []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, at)
        assert size >= 8 and at+size <= len(data)
        result.append((command, at, size))
        at += size
    return result


def uuid(data):
    values = [data[at+8:at+24] for command, at, size in commands(data) if command == 0x1b]
    assert len(values) == 1
    return values[0]


assert uuid(image) == uuid((root/args.reference_image).read_bytes())
bad_header = bytearray(image)
struct.pack_into('<I', bad_header, 36, 4)
header_path = folder/'bad-command-size.dylib'
header_path.write_bytes(bad_header)
bind = next(at for command, at, _ in commands(image) if command in (0x22, 0x80000022))
off, size = struct.unpack_from('<II', image, bind+16)
blob = image[off:off+size]
cursor = 0
while cursor < len(blob):
    start = cursor
    opcode = blob[cursor] & 0xf0
    cursor += 1
    if opcode == 0x70:
        break
    if opcode == 0x40:
        cursor = blob.index(0, cursor)+1
    elif opcode in (0x20, 0x60):
        while blob[cursor] & 128:
            cursor += 1
        cursor += 1
    else:
        assert opcode in (0, 0x10, 0x30, 0x50, 0x90)
else:
    raise ValueError('No segment-selection binding opcode')
bad_binding = bytearray(image)
assert len([row for row in commands(image) if row[0] == 0x19]) < 15
bad_binding[off+start] = 0x7f
binding_path = folder/'bad-binding-segment.dylib'
binding_path.write_bytes(bad_binding)
tool = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/dyld_info'
installed = 'runtime/state/prefix'+tool
extracted = 'runtime/xcode-extract/Xcode.app/Contents/Developer'+tool.split('/Contents/Developer', 1)[1]
assert sha(installed) == sha(extracted)
script = folder/'validate.sh'
lines = ['#!/bin/bash', 'ulimit -c 0', 'unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for label, path in [('valid', root/args.image), ('bad-header', header_path), ('bad-binding', binding_path)]:
    lines += [shlex.join([tool, '-validate_only', '/Volumes/SystemRoot/workspace/'+str(path.relative_to(root))]),
              'status=$?', 'printf "APPLE_DYLD_CASE '+label+' %s\\n" "$status"']
lines.append('exit 0')
script.write_text('\n'.join(lines)+'\n')
module = runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p = module['profile'](stage=args.stage)
command = p['command'][:-2]+['/bin/bash', '/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
command[3] = '90'
environment = module['environment'](p)
for name in ['DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY']:
    environment.pop(name, None)
log = folder/'run.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, env=environment, stdout=out, stderr=subprocess.STDOUT)
text = log.read_text()
statuses = re.findall(r'^APPLE_DYLD_CASE (\S+) (\d+)$', text, re.M)
verified = result.returncode == 0 and statuses == [('valid', '0'), ('bad-header', '1'), ('bad-binding', '1')]
assert sha(args.image) == hashlib.sha256(image).hexdigest() and sha(installed) == sha(extracted)
record = dict(verified=verified, format_validation_only=True, runtime_execution_verified=False,
    image=args.image, image_sha256=sha(args.image), original_uuid=uuid(image).hex(),
    reference_image_sha256=sha(args.reference_image), tool=tool, tool_sha256=sha(installed),
    original_tool_bytes_equal_extracted=True, stage=args.stage, command=command,
    outer_status=result.returncode, cases=statuses, log=str(log.relative_to(root)), log_sha256=sha(log.relative_to(root)),
    sources={'scripts/probe-original-dyld-validation.py': sha('scripts/probe-original-dyld-validation.py')})
(folder/'result.json').write_text(json.dumps(record, indent=2)+'\n')
print(text[-3500:])
print('EVIDENCE', folder/'result.json')
raise SystemExit(0 if verified else 1)
