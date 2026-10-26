#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/crypto-quarantine-runtime-profile.py'))
verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
def profile(include_system_resources=True,old_kernel_control=False):
    p=m['profile'](include_system_resources);stage=json.loads((root/'artifacts/quarantine-vfs-runtime-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    assert stage['previous_source_runtime']==p['source_runtime']
    for key in ['kernel_build','server_build']:assert digest(stage[key])==stage[key+'_sha256']
    kernel=json.loads((root/stage['kernel_build']).read_text());server=json.loads((root/stage['server_build']).read_text())
    for item in kernel['sources']:verify_source(item)
    for name,sha in {**kernel['metadata_source_headers'],**server['source_files'],**stage['source_files']}.items():verify_source(dict(source=name,sha256=sha))
    for item in stage['source_runtime'].values():assert digest(item['path'])==item['sha256']
    selected=stage['source_runtime']
    if old_kernel_control:
        selected={k:dict(v) for k,v in p['source_runtime'].items()};selected['LINUXCODE_DARLING_SERVER']=stage['source_runtime']['LINUXCODE_DARLING_SERVER']
    return {**p,'source_runtime':selected,'source_quarantine_vfs':stage,'old_kernel_control':old_kernel_control}
def environment(p):return m['environment'](p)
