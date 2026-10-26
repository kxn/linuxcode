#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/iokitd-power-runtime-profile.py'))
def profile(include_system_resources=True):
    p=parent['profile'](include_system_resources)
    d=json.loads((root/'artifacts/iokitd-matching-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    assert d['previous_source_runtime']==p['source_runtime']
    assert digest(d['source_build'])==d['source_build_sha256']
    for key in ['notifyd_job_source','notifyd_job','notifyd_binary']:assert digest(d[key])==d[key+'_sha256']
    verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
    assert digest(d['source_notifyd_build'])==d['source_notifyd_build_sha256']
    for item in d['source_notifyd']['sources']:verify(item)
    for name,sha in d['source_notifyd']['headers'].items():verify(dict(source=name,sha256=sha))
    for item in d['source_iokitd']['sources']:verify(item)
    for name,sha in d['source_iokitd']['headers'].items():verify(dict(source=name,sha256=sha))
    assert digest(d['variant_root']+'/usr/sbin/iokitd')==d['source_iokitd']['binary_sha256']
    for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':d['source_runtime'],'source_iokitd_matching':d}
def environment(p):return parent['environment'](p)
