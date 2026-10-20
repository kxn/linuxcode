#!/usr/bin/env python3
"""Add verified original framework trees to a new immutable resource overlay."""
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
parser.add_argument('--graphics-stage', required=True)
parser.add_argument('--target', action='append', required=True)
parser.add_argument('--tag', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
assert len(args.target) == len(set(args.target))
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
resolve = runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
parent = json.loads((root/args.parent).read_text())
graphics = json.loads((root/args.graphics_stage).read_text())
for record in (parent, graphics):
    for path, expected in record['files'].items():
        resolve(path, expected)
    for path, destination in record.get('links', {}).items():
        assert os.readlink(root/path) == destination
pins = json.loads((root/'config/coregraphics-image-pins.json').read_text())
graphics_root = Path(graphics['library']).parents[4]
assert str(graphics_root).startswith('runtime/coregraphics-native-')
old_root = Path(parent['frameworks']).parent
assert (root/old_root).resolve().is_relative_to(root/'runtime')
folder = root/('runtime/resource-framework-overlay-'+args.tag)
output = root/('artifacts/resource-framework-overlay-'+args.tag+'-stage.json')
assert not folder.exists() and not output.exists()
additions = []
for target in args.target:
    pin = pins[target]
    path = pin['path']
    assert path.startswith('/') and '..' not in Path(path).parts and '.framework/' in path
    outer, suffix = path.split('.framework/', 1)
    name = Path(outer).name+'.framework'
    assert not (root/old_root/'frameworks'/name).exists()
    entry = next(row for row in graphics['dependencies'] if row['target'] == target)
    rebuilt = json.loads((root/entry['reconstruction']).read_text())
    source = graphics_root/'frameworks'/name
    image = source/suffix
    assert sha(str(image)) == rebuilt['staged_image_sha256'] == sha(entry['source'])
    assert sha('runtime/fullsystem-libraries'+path) == pin['sha256'] == rebuilt['original_image_sha256']
    assert rebuilt['rip_instructions_patched'] == 0 and not rebuilt['backend_call_overrides']
    additions.append(dict(target=target, framework=name, source=str(source), image=str(image),
                          image_sha256=sha(str(image)), reconstruction=entry['reconstruction']))
trees={}
for item in additions:
    # A facade and its embedded framework belong to one verified tree.
    # All targets sharing the outer name must refer to the same source tree;
    # existing overlay trees still cause refusal above rather than overwrite.
    previous=trees.setdefault(item['framework'],item['source'])
    assert previous==item['source'], 'Conflicting original framework trees'
shutil.copytree(root/old_root, folder, symlinks=True)
for name,source in trees.items():
    shutil.copytree(root/source, folder/'frameworks'/name, symlinks=True)
framework_root = folder/'frameworks'
frameworks = [path for path in framework_root.rglob('*.framework')
              if path.is_dir() and not path.is_symlink()]
leaves = {}
for path in frameworks:
    assert path.name not in leaves, 'Ambiguous framework search name: '+path.name
    leaves[path.name] = path
# Classic dyld searches the innermost Foo.framework suffix, including for
# embedded frameworks. Preserve the native tree and expose its parent search
# directories, rather than changing install names or flattening binaries.
extra_framework_paths = sorted({str(path.parent.relative_to(root)) for path in frameworks
                                if path.parent != framework_root})
# Embedded dylibs use the library search path, rather than the framework
# suffix search. Expose only explicitly selected dylib targets and retain
# existing reviewed paths when the immutable overlay directory moves.
extra_library_paths = {str((folder/Path(path).relative_to(old_root)).relative_to(root))
                       for path in parent.get('extra_library_paths', [])}
for item in additions:
    if Path(item['image']).name.endswith('.dylib'):
        image=framework_root/Path(item['image']).relative_to(graphics_root/'frameworks')
        assert image.is_file() and sha(str(image))==item['image_sha256']
        extra_library_paths.add(str(image.parent.relative_to(root)))
record = {**parent, 'frameworks': str((folder/'frameworks').relative_to(root)),
    'libraries': str((folder/'libraries').relative_to(root)),
    'parent_overlay': args.parent, 'parent_overlay_sha256': sha(args.parent),
    'graphics_stage': args.graphics_stage, 'graphics_stage_sha256': sha(args.graphics_stage),
    'added_original_frameworks': additions, 'runtime_execution_verified': False,
    'added_framework_trees': trees,
    'extra_framework_paths': extra_framework_paths,
    'extra_library_paths': sorted(extra_library_paths),
    'installed': False, 'files': dict(parent['files']), 'links': dict(parent.get('links', {}))}
for path in [args.parent, args.graphics_stage, 'config/coregraphics-image-pins.json',
             str(Path(__file__).relative_to(root))]:
    record['files'][path] = sha(path)
record['files'].update({str(p.relative_to(root)): sha(str(p.relative_to(root)))
    for p in folder.rglob('*') if p.is_file() and not p.is_symlink()})
record['links'].update({str(p.relative_to(root)): os.readlink(p)
    for p in folder.rglob('*') if p.is_symlink()})
output.write_text(json.dumps(record, indent=2)+'\n')
print(output.relative_to(root))
