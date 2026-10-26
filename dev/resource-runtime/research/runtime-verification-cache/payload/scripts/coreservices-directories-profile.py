#!/usr/bin/env python3
"""Select a full source coreservices build without changing the default runtime."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/commoncrypto-original-profile.py'))
def profile(include_system_resources=True,baseline=False):
    p=m['profile'](include_system_resources)
    digest=lambda n:verified_digest((root/n))
    n='artifacts/coreservices-directories-'+('baseline' if baseline else 'source-v2')+'-build.json';d=json.loads((root/n).read_text());history=json.loads((root/'artifacts/dirhelper-source-history/manifest.json').read_text())
    assert d['full_component_source_build'] and d['complete_source_files']==3 and d['exports_preserved']==8
    assert d['previous_source_runtime']==p['source_runtime']
    for item in d['sources']:assert digest(item['source'])==item['sha256'],item['source']
    for path,sha in d['source_headers'].items():
        if baseline and path in history and sha==history[path]['sha256']:path=history[path]['archived']
        assert digest(path)==sha,path
    assert digest(d['library'])==digest(d['variant_root']+'/usr/lib/system/libsystem_coreservices.dylib')==d['library_sha256']
    for key,item in d['source_runtime'].items():assert digest(item['path'])==item['sha256']==p['source_runtime'][key]['sha256']
    return {**p,'source_runtime':d['source_runtime'],'source_coreservices_directories':d}
def environment(p):return m['environment'](p)
