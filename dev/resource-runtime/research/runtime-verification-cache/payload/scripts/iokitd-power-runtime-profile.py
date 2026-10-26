#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/log-compose-runtime-profile.py'))
def profile(include_system_resources=True,baseline=False):
    p=parent['profile'](include_system_resources)
    d=json.loads((root/('artifacts/iokitd-power-'+('baseline-' if baseline else '')+'stage.json')).read_text())
    digest=lambda n:verified_digest((root/n))
    assert d['previous_source_runtime']==p['source_runtime'] and d['baseline']==baseline
    assert digest(d['source_build'])==d['source_build_sha256']
    verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
    if d.get('source_ipc_server'):
        for name,sha in d['source_ipc_server']['source_files'].items():verify(dict(source=name,sha256=sha))
    for item in d['source_iokitd']['sources']:verify(item)
    for name,sha in d['source_iokitd']['headers'].items():verify(dict(source=name,sha256=sha))
    assert digest(d['variant_root']+'/usr/sbin/iokitd')==d['source_iokitd']['binary_sha256']
    for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':d['source_runtime'],'source_iokitd_power':d}
def environment(p):return parent['environment'](p)
