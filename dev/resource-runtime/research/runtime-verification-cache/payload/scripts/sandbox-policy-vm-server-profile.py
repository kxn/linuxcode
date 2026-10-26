#!/usr/bin/env python3
"""Private server with original bytecode decoding; attachment still fails."""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib, json, runpy
root = Path(__file__).resolve().parent.parent
m = runpy.run_path(str(root / 'scripts/sandbox-compiler-resources-profile.py'))
verify_source = runpy.run_path(str(root / 'scripts/verify-historical-source.py'))['verify']
def profile(include_system_resources=True):
    p = m['profile'](include_system_resources)
    d = json.loads((root / 'artifacts/sandbox-policy-vm-server-build.json').read_text())
    digest = lambda n: verified_digest((root / n))
    assert d['previous_source_runtime'] == p['source_runtime']
    for name, sha in d['source_files'].items():
        verify_source(dict(source=name,sha256=sha))
    for item in d['source_runtime'].values():
        assert digest(item['path']) == item['sha256']
    assert d['engine_called_by_runtime'] and not d['profile_application_implemented']
    return {**p, 'source_runtime': d['source_runtime'], 'source_sandbox_policy_vm': d}
def environment(p): return m['environment'](p)
