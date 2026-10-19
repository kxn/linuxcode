#!/usr/bin/env python3
"""Stage the complete pinned Intel CoreGraphics experiment without installing it."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--dependency', action='append', default=[])
parser.add_argument('--simd-stage')
parser.add_argument('--with-resources', action='store_true')
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder = root / ('runtime/coregraphics-native-' + args.tag)
output = root / ('artifacts/coregraphics-native-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists()
digest = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
manifest = 'config/coregraphics-image-pins.json'
pin = json.loads((root / manifest).read_text())['coregraphics-resource-native']
original = 'runtime/fullsystem-libraries' + pin['path']
source = 'runtime/rebuilt-coregraphics-resource-native/CoreGraphics'
reconstruction = 'runtime/rebuilt-coregraphics-resource-native/reconstruction.json'
report = json.loads((root / reconstruction).read_text())
assert digest(original) == pin['sha256'] == report['original_image_sha256']
assert digest(source) == report['staged_image_sha256']
assert not report['modern_adapter'] and not report['redirected_imports'] and not report['backend_call_overrides']
framework = folder / 'frameworks/CoreGraphics.framework'
library = framework / 'Versions/A/CoreGraphics'
library.parent.mkdir(parents=True)
shutil.copy2(root / source, library)
(framework / 'Versions/Current').symlink_to('A')
(framework / 'CoreGraphics').symlink_to('Versions/Current/CoreGraphics')
record = dict(library=str(library.relative_to(root)), original=original,
              original_sha256=digest(original), reconstruction=reconstruction,
              files={p: digest(p) for p in [manifest, original, source, reconstruction, str(library.relative_to(root))]},
              installed=False, runtime_execution_verified=False,
              complete_original_image=True, resource_compilation_verified=False)
record['resource_inputs'] = {}
def copy_resources(framework, pin):
    resource = root / 'runtime/recovery/macOS Base System' / (str(Path(pin['path']).parent / 'Resources').lstrip('/'))
    if not args.with_resources or not resource.is_dir():
        return
    destination = framework/'Versions/A/Resources'
    shutil.copytree(resource, destination, symlinks=True)
    (framework/'Resources').symlink_to('Versions/Current/Resources')
    for path in resource.rglob('*'):
        if path.is_file():
            name = str(path.relative_to(root))
            record['resource_inputs'][name] = digest(name)
copy_resources(framework, pin)
pins = json.loads((root / manifest).read_text())
record['dependencies'] = []
for target in args.dependency:
    pin = pins[target]
    name = Path(pin['path']).name
    source = 'runtime/rebuilt-' + target + '/' + name
    reconstruction = 'runtime/rebuilt-' + target + '/reconstruction.json'
    report = json.loads((root / reconstruction).read_text())
    original = 'runtime/fullsystem-libraries' + pin['path']
    assert digest(original) == pin['sha256'] == report['original_image_sha256']
    assert digest(source) == report['staged_image_sha256']
    assert not report['modern_adapter'] and not report['redirected_imports'] and not report['backend_call_overrides']
    if name.endswith('.dylib'):
        destination = folder / 'libraries' / name
    else:
        framework = folder / ('frameworks/' + name + '.framework')
        destination = framework / ('Versions/A/' + name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / source, destination)
    if not name.endswith('.dylib'):
        (framework / 'Versions/Current').symlink_to('A')
        (framework / name).symlink_to('Versions/Current/' + name)
        copy_resources(framework, pin)
    record['dependencies'].append(dict(target=target, source=source, reconstruction=reconstruction))
    record['files'].update({p: digest(p) for p in [source, original, reconstruction, str(destination.relative_to(root))]})
if args.simd_stage:
    simd = json.loads((root / args.simd_stage).read_text())
    for p, expected in simd['files'].items():
        assert digest(p) == expected, p
    record['files'].update(simd['files'])
    record['files'][args.simd_stage] = digest(args.simd_stage)
    for path in [simd['helper'], simd['library'], *simd.get('additional_libraries',[])]:
        destination = folder / 'libraries' / Path(path).name
        assert not destination.exists()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, destination)
        record['files'][str(destination.relative_to(root))] = digest(str(destination.relative_to(root)))
    record['simd_stage'] = args.simd_stage
record['files'].update(record['resource_inputs'])
record['files'].update({str(p.relative_to(root)):digest(str(p.relative_to(root)))
                        for p in folder.rglob('*') if p.is_file() and not p.is_symlink()})
record['links'] = {str(p.relative_to(root)):os.readlink(p) for p in folder.rglob('*') if p.is_symlink()}
output.write_text(json.dumps(record, indent=2) + '\n')
print(output.relative_to(root))
