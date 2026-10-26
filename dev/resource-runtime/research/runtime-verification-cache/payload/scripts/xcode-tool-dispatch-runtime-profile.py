#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib, json, runpy
root = Path(__file__).resolve().parent.parent
parent = runpy.run_path(str(root / 'scripts/metadata-root-name-runtime-profile.py'))
def profile(diagnostic=False):
    p = parent['profile'](diagnostic=diagnostic)
    data = json.loads((root / 'artifacts/xcode-tool-dispatch-stage-v2.json').read_text())
    chosen = data['runtimes']['diagnostic' if diagnostic else 'normal']
    digest = lambda name: verified_digest((root / name))
    assert chosen['previous_source_runtime'] == p['source_runtime']
    for item in chosen['source_runtime'].values(): assert digest(item['path']) == item['sha256']
    for name, sha in chosen['files'].items(): assert digest(name) == sha
    assert digest(chosen['system_version_binding']) == chosen['system_version_binding_sha256']
    return {**p, 'source_runtime': chosen['source_runtime'], 'system_version_binding': chosen['system_version_binding'],
            'source_tool_dispatch': data, 'tool_dispatch_selected_runtime': chosen}
def environment(p): return parent['environment'](p)
