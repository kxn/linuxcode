#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/unrestricted-sandbox-runtime-profile.py'))
def profile(include_system_resources=True,diagnostic=False):
    p=m['profile'](include_system_resources)
    d=json.loads((root/('artifacts/fsevents-device-'+('diagnostic' if diagnostic else 'runtime')+'-stage.json')).read_text())
    digest=lambda n:verified_digest((root/n))
    assert d['previous_source_runtime']==p['source_runtime'] and d['test_only']==diagnostic
    for key in ['server_build','kernel_build']:assert digest(d[key])==d[key+'_sha256']
    server=json.loads((root/d['server_build']).read_text());kernel=json.loads((root/d['kernel_build']).read_text())
    verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
    for name,sha in server['source_files'].items():verify(dict(source=name,sha256=sha))
    for item in kernel['sources']:verify(item)
    for name,sha in kernel['metadata_source_headers'].items():verify(dict(source=name,sha256=sha))
    for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
    if diagnostic:
        for key in ['original_policy','selected_policy']:assert digest(d['diagnostic_policy'][key])==d['diagnostic_policy'][key+'_sha256']
    return {**p,'source_runtime':d['source_runtime'],'source_fsevents_device':d,
            'coreservices_diagnostic_policy':d['diagnostic_policy']}
def environment(p):return m['environment'](p)
