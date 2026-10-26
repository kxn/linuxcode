#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/sandbox-fs-runtime-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/unrestricted-sandbox-runtime-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
    assert d['previous_source_runtime']==p['source_runtime']
    for key in ['server_build','xpc_build']:assert digest(d[key])==d[key+'_sha256']
    server=json.loads((root/d['server_build']).read_text());xpc=json.loads((root/d['xpc_build']).read_text())
    for name,sha in server['source_files'].items():verify_source(dict(source=name,sha256=sha))
    for name,sha in {**xpc['source_files'],**xpc['modified_files']}.items():verify_source(dict(source='vendor/darling/src/external/libxpc/'+name,sha256=sha))
    for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':d['source_runtime'],'source_unrestricted_sandbox':d}
def environment(p):return m['environment'](p)
