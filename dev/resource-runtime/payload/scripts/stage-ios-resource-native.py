#!/usr/bin/env python3
"""Stage the reconstructed CoreSVG privately for original resource tools."""
from pathlib import Path
import hashlib, json, os, shutil

root = Path(__file__).resolve().parent.parent
digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
report_name = 'runtime/rebuilt-coresvg-resource-native/reconstruction.json'
report = json.loads((root / report_name).read_text())
source = 'runtime/rebuilt-coresvg-resource-native/CoreSVG'
pin = json.loads((root / 'config/ios-resource-image-pins.json').read_text())['coresvg-resource-native']
original = 'runtime/fullsystem-libraries' + pin['path']
assert digest(original) == pin['sha256'] == report['original_image_sha256']
assert digest(source) == report['staged_image_sha256']
assert report['exports'] == 298 and not report['modern_adapter']
assert not report['backend_call_overrides'] and not report['redirected_imports']
folder = root / 'runtime/ios-resource-native'
assert not folder.exists(), 'Keep existing staged runtimes immutable'
framework = folder / 'frameworks/CoreSVG.framework'
version = framework / 'Versions/A'
version.mkdir(parents=True)
shutil.copy2(root / source, version / 'CoreSVG')
resource = root / 'runtime/recovery/macOS Base System/System/Library/PrivateFrameworks/CoreSVG.framework/Versions/A/Resources'
if resource.exists(): shutil.copytree(resource, version / 'Resources')
(framework / 'Versions/Current').symlink_to('A')
(framework / 'CoreSVG').symlink_to('Versions/Current/CoreSVG')
if (version / 'Resources').exists(): (framework / 'Resources').symlink_to('Versions/Current/Resources')
record = dict(original=original, original_sha256=digest(original), source=source, source_sha256=digest(source),
    reconstruction=report_name, reconstruction_sha256=digest(report_name), exports=report['exports'],
    files={str(path.relative_to(root)): digest(path) for path in folder.rglob('*') if path.is_file()},
    links={str(path.relative_to(root)): os.readlink(path) for path in folder.rglob('*') if path.is_symlink()},
    installed=False, resource_compilation_verified=False)
(root / 'artifacts/ios-resource-native-stage.json').write_text(json.dumps(record, indent=2) + '\n')
print('Staged original CoreSVG privately; resource tool execution remains to verify')
