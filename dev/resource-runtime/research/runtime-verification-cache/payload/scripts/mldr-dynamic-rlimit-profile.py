#!/usr/bin/env python3
"""Select the isolated source loader that handles changing descriptor limits."""
from pathlib import Path
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']

def select(p, stage):
    data = json.loads((root / stage).read_text())
    for path, digest in data['files'].items():
        if path.startswith(('scripts/', 'vendor/')):
            resolve(path, digest)
        else:
            assert verified_digest((root / path)) == digest, path
    assert p['source_runtime'] == data['previous_source_runtime']
    return {**p, 'source_runtime': data['source_runtime'], 'mldr_dynamic_rlimit_stage': stage}

def profile(stage='artifacts/mldr-dynamic-rlimit-v1-stage.json'):
    data = json.loads((root / stage).read_text())
    parent = runpy.run_path(str(root / data['parent_profile']))
    return select(parent['profile'](**data.get('parent_profile_arguments', {})), stage)

def environment(p):
    data = json.loads((root / p['mldr_dynamic_rlimit_stage']).read_text())
    return runpy.run_path(str(root / data['parent_profile']))['environment'](p)
