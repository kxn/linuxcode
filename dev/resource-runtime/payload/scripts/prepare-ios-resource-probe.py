#!/usr/bin/env python3
"""Create the two reviewed version-probe jobs; never replace another job."""
from pathlib import Path
import hashlib
import json
root = Path(__file__).resolve().parent.parent
folder = root / 'runtime/ios-resource-probe'
expected = {}
for name in ('actool', 'ibtool'):
    expected[name + '.sh'] = ('#!/bin/bash\ncd /Volumes/SystemRoot/workspace/runtime/ios-resource-probe\n'
        'ulimit -c 0\n/Applications/Xcode.app/Contents/Developer/usr/bin/' + name + ' --version\n'
        'status=$?\nprintf "ORIGINAL_RESOURCE_TOOL_STATUS %s\\n" "$status"\nexit "$status"\n').encode()
if folder.is_symlink():
    raise SystemExit('Probe job directory must not be a symlink')
# Validate both jobs before creating either file.
for name, content in expected.items():
    path = folder / name
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != content)):
        raise SystemExit('Existing different probe job preserved: ' + str(path))
folder.mkdir(parents=True, exist_ok=True)
for name, content in expected.items():
    path = folder / name
    if not path.exists():
        with path.open('xb') as stream:
            stream.write(content)
print(json.dumps({'runtime_execution': False,
    'jobs': {str((folder / name).relative_to(root)): hashlib.sha256(content).hexdigest()
             for name, content in expected.items()}}, indent=2))
