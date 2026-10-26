#!/usr/bin/env python3
"""Select an immutable server candidate over the source-built loader stage."""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/mldr-dynamic-rlimit-profile.py'))
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']

def select(p, stage):
    data = json.loads((root / stage).read_text())
    assert p['source_runtime'] == data['previous_source_runtime']
    for name, digest in data.get('files', {}).items():
        if name.startswith(('scripts/', 'vendor/')):
            resolve(name, digest)
        else:
            assert verified_digest((root / name)) == digest, name
    for value in data['source_runtime'].values():
        assert verified_digest((root / value['path'])) == value['sha256']
    return {**p, 'source_runtime': data['source_runtime'], 'shared_remap_stage': stage,
        'system_version_binding': data.get('system_version_binding', p['system_version_binding'])}

def profile(stage):
    data = json.loads((root / stage).read_text())
    return select(parent['profile'](stage=data['parent_stage']), stage)

def environment(p):
    return parent['environment'](p)
