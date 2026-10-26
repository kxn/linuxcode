#!/usr/bin/env python3
"""Select the complete Intel CoreGraphics experiment over the resource closure."""
from pathlib import Path
import hashlib
import json
import os
import runpy

root = Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent = runpy.run_path(str(root / 'scripts/ios-resource-closure-profile.py'))
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']

def profile(stage='artifacts/ios-resource-io80211-v1-stage.json',
            graphics_stage='artifacts/coregraphics-native-v1-stage.json',
            include_resource_environment=True):
    p = parent['profile'](stage=stage)
    data = json.loads((root / graphics_stage).read_text())
    for path, digest in data['files'].items():
        if path.startswith(('config/', 'scripts/', 'vendor/')):
            resolve(path, digest)
        else:
            assert verified_digest((root / path)) == digest, path
    for path, target in data.get('links',{}).items():
        assert os.readlink(root/path) == target, path
    caller = p if include_resource_environment else runpy.run_path(
        str(root / 'scripts/xcode-tool-dispatch-runtime-profile.py'))['profile']()
    command = list(caller['command'])
    framework_dir = str(Path(data['library']).parents[3])
    index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_FRAMEWORK_PATH='))
    command[index] = 'DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/' + framework_dir + ':' + command[index].split('=', 1)[1]
    library_dir = Path(framework_dir).parent / 'libraries'
    if (root / library_dir).is_dir():
        index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
        command[index] = 'DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/' + str(library_dir) + ':' + command[index].split('=', 1)[1]
    return {**p, 'command': command, 'source_original_coregraphics': data,
            'original_coregraphics_stage': graphics_stage}

def environment(p):
    return parent['environment'](p)
