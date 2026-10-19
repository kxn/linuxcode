#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, runpy

root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/xcode-tool-dispatch-runtime-profile.py'))
def profile(diagnostic=False):
    p = parent['profile'](diagnostic=diagnostic)
    data = json.loads((root / 'artifacts/ios-resource-native-stage.json').read_text())
    digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
    for name, sha in data['files'].items(): assert digest(name) == sha
    assert digest(data['reconstruction']) == data['reconstruction_sha256']
    command = list(p['command'])
    index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_FRAMEWORK_PATH='))
    command[index] = 'DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/ios-resource-native/frameworks:' + command[index].split('=', 1)[1]
    return {**p, 'command': command, 'source_ios_resource_frameworks': data}
def environment(p): return parent['environment'](p)
