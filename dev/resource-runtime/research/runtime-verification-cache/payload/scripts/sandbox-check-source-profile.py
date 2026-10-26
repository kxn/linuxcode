#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/typed-new-delete-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources)
    stage=json.loads((root/'artifacts/sandbox-check-source-build.json').read_text());digest=lambda n:verified_digest((root/n))
    assert stage['previous_source_runtime']==p['source_runtime']
    verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
    for name,sha in stage['source_files'].items():verify(dict(source=name,sha256=sha))
    for item in stage['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':stage['source_runtime'],'source_sandbox_checks':stage}
def environment(p):return m['environment'](p)
