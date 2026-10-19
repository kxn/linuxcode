#!/usr/bin/env python3
"""Select one full source-built libSystem without modifying the default runtime."""
from pathlib import Path
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/shared-remap-runtime-profile.py'))
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']

def select(p, stage):
    data = json.loads((root / stage).read_text())
    assert data['full_initializer_and_queue_source_build']
    for name, digest in {**data['files'], **data['link_inputs']}.items():
        resolve(name, digest)
    objects = json.loads((root / data['object_report']).read_text())
    for name, digest in objects['sources'].items():
        resolve(name, digest)
    assert hashlib.sha256((root / data['output']).read_bytes()).hexdigest() == data['output_sha256']
    command = list(p['command'])
    index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
    command[index] = 'DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/' + str(Path(data['output']).parent) + ':' + command[index].split('=', 1)[1]
    return {**p, 'command': command, 'libsystem_kqueue_build': stage}

def profile(stage):
    data = json.loads((root / stage).read_text())
    return select(parent['profile'](stage=data['stage']), stage)

def environment(p):
    return parent['environment'](p)
