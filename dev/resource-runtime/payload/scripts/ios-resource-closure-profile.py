#!/usr/bin/env python3
"""Use a verified private resource framework set over the existing Xcode runtime."""
from pathlib import Path
import hashlib, json, os, runpy
root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/xcode-tool-dispatch-runtime-profile.py'))
def profile(diagnostic=False, stage='artifacts/ios-resource-coretheme-stage.json'):
    p = parent['profile'](diagnostic=diagnostic)
    data = json.loads((root / stage).read_text())
    digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
    for name, sha in data['files'].items(): assert digest(name) == sha, name
    for name, target in data['links'].items(): assert os.readlink(root / name) == target, name
    for item in data['components']:
        assert digest(item['reconstruction']) == item['reconstruction_sha256']
    command = list(p['command'])
    index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_FRAMEWORK_PATH='))
    command[index] = 'DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/' + data['folder'] + '/frameworks:' + command[index].split('=', 1)[1]
    if (root / data['folder'] / 'libraries').is_dir():
        index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
        command[index] = 'DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/' + data['folder'] + '/libraries:' + command[index].split('=', 1)[1]
    return {**p, 'command': command, 'source_ios_resource_frameworks': data}
def environment(p): return parent['environment'](p)
