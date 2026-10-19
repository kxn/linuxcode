#!/usr/bin/env python3
"""Inventory missing original strong dependencies against an observed tool scope.

This models file search candidates only. It does not verify dyld resolution,
symbols, initializer order, API compatibility, or optional runtime dlopen paths.
It never modifies pins, libraries or runtime stages.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', action='append', required=True)
parser.add_argument('--target-manifest', default='config/coregraphics-image-pins.json')
parser.add_argument('--scope-probe', required=True)
parser.add_argument('--graphics-stage', required=True)
parser.add_argument('--runtime-stage', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
read = lambda path: json.loads((root/path).read_text())
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
output = root/args.output
assert not output.exists()
pins = read(args.target_manifest)
probe = read(args.scope_probe)
observed = read(probe['scope']['configuration'])
old_graphics = Path(read(observed['graphics_stage'])['library']).parents[4]
new_graphics = Path(read(args.graphics_stage)['library']).parents[4]
private = Path(read(args.runtime_stage)['system_library']).parents[1]/'darling-root'


def host(path):
    prefix = '/Volumes/SystemRoot/workspace/'
    if path.startswith(prefix):
        relative = Path(path[len(prefix):])
        if relative.is_relative_to(old_graphics):
            relative = new_graphics/relative.relative_to(old_graphics)
        return root/relative
    return root/'runtime/state/prefix'/path.lstrip('/')


scope = probe['scope']['tool_environment']
frameworks = [host(path) for path in scope['DYLD_FRAMEWORK_PATH'].split(':')]
libraries = [host(path) for path in scope['DYLD_LIBRARY_PATH'].split(':')]


def candidates(path):
    paths = [root/'runtime/state/prefix'/path.lstrip('/'), root/private/path.lstrip('/')]
    if '.framework/' in path:
        stem, rest = path.split('.framework/', 1)
        name = Path(stem).name+'.framework'
        paths += [folder/name/rest for folder in frameworks]
        paths += [folder/name/Path(rest).name for folder in frameworks]
    paths += [folder/Path(path).name for folder in libraries]
    return [str(path.relative_to(root)) for path in paths if path.is_file()]


queue = []
for target in args.target:
    pin = pins[target]
    assert pin['reference_set'] == 'fullsystem'
    assert sha('runtime/fullsystem-libraries'+pin['path']) == pin['sha256']
    queue.append(pin['path'])
images, weak, unavailable = {}, set(), []
for path in queue:
    if path in images:
        continue
    original = root/'runtime/fullsystem-libraries'/path.lstrip('/')
    if not original.is_file():
        unavailable.append(path)
        continue
    data = original.read_bytes()
    assert data[:8] == bytes.fromhex('cffaedfe07000001')
    at, dependencies = 32, []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, at)
        if command in (0xc, 0x80000018, 0x8000001f, 0x80000023):
            start = at+struct.unpack_from('<I', data, at+8)[0]
            dependency = data[start:data.index(0, start)].decode()
            found = candidates(dependency)
            dependencies.append(dict(path=dependency, load_command=hex(command), file_candidates=found))
            if not found:
                if command == 0x80000018:
                    weak.add(dependency)
                elif dependency not in queue:
                    queue.append(dependency)
        at += size
    images[path] = dict(original_sha256=hashlib.sha256(data).hexdigest(), original_bytes=len(data),
                        dependencies=dependencies)
report = dict(diagnostic_only=True, dyld_resolution_verified=False, api_compatibility_verified=False,
    scope_probe=args.scope_probe, graphics_stage=args.graphics_stage, runtime_stage=args.runtime_stage,
    target_manifest=args.target_manifest, targets=args.target,
    images=images, weak_missing_not_queued=sorted(weak), unavailable_originals=unavailable,
    inputs={path: sha(path) for path in [args.scope_probe, args.graphics_stage, args.runtime_stage, args.target_manifest,
                                        str(Path(__file__).relative_to(root))]})
output.write_text(json.dumps(report, indent=2)+'\n')
print('PLAN', args.output, 'images', len(images), 'unavailable', len(unavailable))
for path, image in images.items():
    print(Path(path).name, image['original_bytes'])
