#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/launchd-sandbox-source-profile.py'))
def profile(include_system_resources=True,capture=False):
    p=m['profile'](include_system_resources)
    n='artifacts/sandbox-fs-mutations-'+('capture' if capture else 'source')+'-stage.json'
    d=json.loads((root/n).read_text());digest=lambda n:verified_digest((root/n))
    verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
    assert d['test_only']==capture and d['previous_source_runtime']==p['source_runtime']
    assert digest(d['kernel_build'])==d['kernel_build_sha256']
    build=json.loads((root/d['kernel_build']).read_text())
    for item in build['sources']:
        verify_source(item)
        if 'test_override_for' in item:assert digest(item['test_override_for'])==item['production_source_sha256']
    for path,sha in {**build['metadata_source_headers'],**d['extra_source_headers']}.items():verify_source(dict(source=path,sha256=sha))
    for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':d['source_runtime'],'source_sandbox_fs':d}
def environment(p):return m['environment'](p)
