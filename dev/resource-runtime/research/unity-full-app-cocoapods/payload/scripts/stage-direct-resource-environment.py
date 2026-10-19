#!/usr/bin/env python3
"""Generate and validate an immutable original-resource-tool environment descriptor."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-stage', required=True)
parser.add_argument('--resource-stage', required=True)
parser.add_argument('--graphics-stage', required=True)
parser.add_argument('--libsystem-build', required=True)
parser.add_argument('--xcode-root', default='/Applications/Xcode.app')
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = (root / args.output).resolve()
assert output.is_relative_to(root) and not output.exists()
assert args.xcode_root.startswith('/') and ':' not in args.xcode_root
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
configuration = {}
for key, value in [('resource_stage', args.resource_stage), ('graphics_stage', args.graphics_stage),
    ('resource_system_build', args.libsystem_build)]:
    path = (root / value).resolve()
    assert path.is_relative_to(root) and path.is_file()
    configuration[key] = str(path.relative_to(root))
    configuration[key+'_sha256'] = sha(path)
configuration['executables'] = [args.xcode_root.rstrip('/') + '/Contents/Developer/usr/bin/' + name for name in ['actool', 'ibtool']]
output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', prefix='.resource-environment-', dir=output.parent, delete=False) as stream:
    temporary = Path(stream.name)
    stream.write(json.dumps(configuration, indent=2)+'\n')
try:
    profile = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))['profile'](
        stage=args.runtime_stage, configuration=str(temporary.relative_to(root)))
    assert profile['direct_resource_environment']['parent_DYLD_paths_changed'] is False
    temporary.replace(output)
finally:
    temporary.unlink(missing_ok=True)
print(json.dumps(dict(configuration=str(output.relative_to(root)), sha256=sha(output),
    validated=True, Darling_started=False, original_resource_compilation_verified=False), indent=2))
