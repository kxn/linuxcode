#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(root/'scripts/global-fsevents-runtime-profile.py'))
def profile(diagnostic=False):
    p=parent['profile'](diagnostic=diagnostic);d=json.loads((root/'artifacts/vchroot-links-stage.json').read_text());digest=lambda n:verified_digest((root/n))
    assert digest(d['kernel_build'])==d['kernel_build_sha256']
    chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['previous_source_runtime']==p['source_runtime']
    for item in chosen['source_runtime'].values():assert digest(item['path'])==item['sha256']
    assert digest(chosen['system_version_binding'])==chosen['system_version_binding_sha256']
    return {**p,'source_runtime':chosen['source_runtime'],'system_version_binding':chosen['system_version_binding'],'source_vchroot_links':d,'vchroot_links_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
