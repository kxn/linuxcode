#!/usr/bin/env python3
"""Select a pinned resolver binding for a private native session."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent.parent


def select(profile, stage):
    data = json.loads((root / stage).read_text())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert data['private_resolver_binding']
    assert digest(root / data['parent_stage']) == data['parent_stage_sha256']
    for name, expected in data['files'].items():
        assert digest(root / name) == expected, name
    command = list(profile['command'])
    assert command.count(data['parent_launcher']) == 1
    command[command.index(data['parent_launcher'])] = data['launcher']
    return {**profile, 'command': command, 'native_resolver_stage': stage}
