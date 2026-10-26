#!/usr/bin/env python3
"""Select the source launchd with enabled audit-token Sandbox checks."""
from pathlib import Path
import hashlib, json, runpy
root = Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m = runpy.run_path(str(root / 'scripts/sandbox-policy-vm-server-profile.py'))
def profile(include_system_resources=True):
    p = m['profile'](include_system_resources)
    d = json.loads((root / 'artifacts/launchd-sandbox-source-build.json').read_text())
    digest = lambda n: verified_digest((root / n))
    assert d['previous_source_runtime'] == p['source_runtime']
    resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
    for name, sha in d['source_files'].items(): resolve(name, sha)
    for item in d['source_runtime'].values(): assert digest(item['path']) == item['sha256']
    return {**p, 'source_runtime': d['source_runtime'], 'source_launchd_sandbox': d}
def environment(p): return m['environment'](p)
