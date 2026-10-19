#!/usr/bin/env python3
"""Select a complete source candidate with an internal Linux procfs mount."""
from pathlib import Path
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/loader-environment-runtime-profile.py'))
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']

def select(p, stage):
    data = json.loads((root / stage).read_text())
    assert p['source_runtime'] == data['previous_source_runtime']
    for name, digest in data['files'].items():
        resolve(name, digest)
    for row in data['source_runtime'].values():
        assert hashlib.sha256((root / row['path']).read_bytes()).hexdigest() == row['sha256']
    assert (root / data['mtab']).is_symlink()
    assert (root / data['mtab']).readlink() == Path(data['mtab_target'])
    command = list(p['command'])
    index = next(i for i, arg in enumerate(command) if arg.startswith('DYLD_LIBRARY_PATH='))
    command[index] = 'DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/' + str(Path(data['system_library']).parent) + ':' + command[index].split('=', 1)[1]
    return {**p, 'command': command, 'source_runtime': data['source_runtime'],
        'system_version_binding': data['system_version_binding'], 'private_procfs_stage': stage}

def profile(stage):
    data = json.loads((root / stage).read_text())
    return select(parent['profile'](data['parent_stage']), stage)

def environment(p):
    return parent['environment'](p)
