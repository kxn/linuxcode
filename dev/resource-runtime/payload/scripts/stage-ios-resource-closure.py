#!/usr/bin/env python3
"""Stage a pinned original resource framework set into a new private directory."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil
root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--target', action='append', required=True)
args = parser.parse_args()
assert re.fullmatch(r'[a-z0-9-]+', args.tag)
folder = root / ('runtime/ios-resource-' + args.tag)
output = root / ('artifacts/ios-resource-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists(), 'Keep previous staged runtimes immutable'
pins = json.loads((root / 'config/ios-resource-image-pins.json').read_text())
digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
components = []
# Validate the entire set before creating any output.
for target in args.target:
    pin = pins[target]
    name = Path(pin['path']).name
    original = 'runtime/fullsystem-libraries' + pin['path']
    source = 'runtime/rebuilt-' + target + '/' + name
    report_name = 'runtime/rebuilt-' + target + '/reconstruction.json'
    report = json.loads((root / report_name).read_text())
    assert digest(original) == pin['sha256'] == report['original_image_sha256']
    assert digest(source) == report['staged_image_sha256']
    assert not report['modern_adapter'] and not report['backend_call_overrides'] and not report['redirected_imports']
    components.append(dict(target=target, name=name, original=original, original_sha256=digest(original),
        source=source, source_sha256=digest(source), reconstruction=report_name,
        reconstruction_sha256=digest(report_name), exports=report['exports']))
output.parent.mkdir(parents=True, exist_ok=True)
for item in components:
    if item['name'].endswith('.dylib'):
        library = folder / 'libraries' / item['name']
        library.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / item['source'], library)
        continue
    framework = folder / ('frameworks/' + item['name'] + '.framework')
    version = framework / 'Versions/A'
    version.mkdir(parents=True)
    shutil.copy2(root / item['source'], version / item['name'])
    resource = root / 'runtime/recovery/macOS Base System' / str(Path(pins[item['target']]['path']).parent / 'Resources').lstrip('/')
    if resource.exists(): shutil.copytree(resource, version / 'Resources')
    (framework / 'Versions/Current').symlink_to('A')
    (framework / item['name']).symlink_to('Versions/Current/' + item['name'])
    if (version / 'Resources').exists(): (framework / 'Resources').symlink_to('Versions/Current/Resources')
record = dict(folder=str(folder.relative_to(root)), components=components,
    files={str(path.relative_to(root)): digest(path) for path in folder.rglob('*') if path.is_file()},
    links={str(path.relative_to(root)): os.readlink(path) for path in folder.rglob('*') if path.is_symlink()},
    installed=False, resource_compilation_verified=False)
output.write_text(json.dumps(record, indent=2) + '\n')
print(output.relative_to(root))
