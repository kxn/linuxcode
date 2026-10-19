#!/usr/bin/env python3
"""Select a coherent loader root while preserving the parent profile chain."""
from pathlib import Path
import json
import runpy
import hashlib

root = Path(__file__).resolve().parent.parent
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']

def select(p, stage):
    data = json.loads((root / stage).read_text())
    assert p['source_runtime'] == data['previous_source_runtime']
    for name, digest in data['files'].items():
        resolve(name, digest)
    for row in data['source_runtime'].values():
        assert hashlib.sha256((root / row['path']).read_bytes()).hexdigest() == row['sha256']
    return {**p, 'source_runtime': data['source_runtime'], 'loader_environment_stage': stage}

def profile(stage):
    data = json.loads((root / stage).read_text())
    parent = runpy.run_path(str(root / data['parent_profile']))
    return select(parent['profile'](**data['parent_profile_arguments']), stage)

def environment(p):
    data = json.loads((root / p['loader_environment_stage']).read_text())
    parent = runpy.run_path(str(root / data['parent_profile']))
    return parent['environment'](p)
