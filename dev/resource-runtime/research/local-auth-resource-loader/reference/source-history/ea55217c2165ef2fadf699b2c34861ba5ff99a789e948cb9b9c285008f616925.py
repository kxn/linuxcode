#!/usr/bin/env python3
"""Extend an immutable graphics experiment with a pinned reconstructed image.

This only creates a separate stage. It neither installs binaries nor claims
that a successfully reconstructed library has passed runtime validation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shutil

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent', required=True)
parser.add_argument('--tag', required=True)
parser.add_argument('--target', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
parent = json.loads((root / args.parent).read_text())
for path, expected in parent['files'].items():
    if path.startswith(('scripts/', 'config/', 'vendor/')):
        resolve(path, expected)
    else:
        assert sha(path) == expected, path
for path, target in parent.get('links', {}).items():
    assert os.readlink(root / path) == target, path
manifest = 'config/coregraphics-image-pins.json'
pin = json.loads((root / manifest).read_text())[args.target]
name = Path(pin['path']).name
source = 'runtime/rebuilt-' + args.target + '/' + name
reconstruction = 'runtime/rebuilt-' + args.target + '/reconstruction.json'
report = json.loads((root / reconstruction).read_text())
original = 'runtime/fullsystem-libraries' + pin['path']
assert sha(original) == pin['sha256'] == report['original_image_sha256']
assert sha(source) == report['staged_image_sha256']
assert not report['installed'] and not report['execution_verified']
assert not report['backend_call_overrides']
folder = root / ('runtime/coregraphics-native-' + args.tag)
output = root / ('artifacts/coregraphics-native-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists()
old_folder = Path(parent['library']).parents[4]
assert str(old_folder).startswith('runtime/coregraphics-native-')
shutil.copytree(root / old_folder, folder, symlinks=True)
if name.endswith('.dylib'):
    destination = folder / 'libraries' / name
else:
    framework = folder / 'frameworks' / (name + '.framework')
    destination = framework / 'Versions/A' / name
assert not destination.exists()
destination.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / source, destination)
if not name.endswith('.dylib'):
    (framework / 'Versions/Current').symlink_to('A')
    (framework / name).symlink_to('Versions/Current/' + name)
record = {**parent, 'library': str(folder / Path(parent['library']).relative_to(old_folder)),
    'installed': False, 'runtime_execution_verified': False, 'resource_compilation_verified': False,
    'parent_stage': args.parent, 'parent_stage_sha256': sha(args.parent),
    'dependencies': [*parent['dependencies'], dict(target=args.target, source=source,
        reconstruction=reconstruction)], 'files': dict(parent['files'])}
record['files'].update({p: sha(p) for p in [args.parent, manifest, source, original, reconstruction,
    'scripts/extend-coregraphics-stage.py', 'scripts/rebuild-c-cache-image.py',
    'scripts/cache-patch-metadata.py', 'config/cache-patch-metadata-format.json']})
record['files'].update({str(p.relative_to(root)): sha(str(p.relative_to(root)))
    for p in folder.rglob('*') if p.is_file() and not p.is_symlink()})
record['links'] = {**parent.get('links', {}), **{str(p.relative_to(root)): os.readlink(p)
    for p in folder.rglob('*') if p.is_symlink()}}
output.write_text(json.dumps(record, indent=2) + '\n')
print(output.relative_to(root))
