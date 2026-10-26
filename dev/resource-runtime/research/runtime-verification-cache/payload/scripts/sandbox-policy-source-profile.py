#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/expected-access-source-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);stage=json.loads((root/'artifacts/sandbox-policy-vfs-baseline.json').read_text())
    digest=lambda n:verified_digest((root/n));assert stage['previous_source_runtime']==p['source_runtime']
    for name,sha in stage['source_files'].items():assert digest(name)==sha
    for item in stage['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':stage['source_runtime'],'source_sandbox_policy':stage}
def environment(p):return m['environment'](p)
