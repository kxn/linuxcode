#!/usr/bin/env python3
"""Original compiler and resources; no sandbox application result is synthesized."""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/sandbox-compiler-native-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/sandbox-compiler-resources-stage.json').read_text());digest=lambda n:verified_digest((root/n))
    assert d['previous_source_runtime']==p['source_runtime']
    for path,item in d['resource_files'].items():assert digest(path)==digest(item['source'])==item['sha256']
    for path,target in d['resource_symlinks'].items():assert str((root/path).readlink())==target
    for key,item in d['source_runtime'].items():assert digest(item['path'])==item['sha256']==p['source_runtime'][key]['sha256']
    assert digest(d['variant_root']+'/usr/lib/system/libsystem_coreservices.dylib')==p['source_coreservices_directories']['library_sha256']
    return {**p,'source_runtime':d['source_runtime'],'original_sandbox_resources':d}
def environment(p):return m['environment'](p)
