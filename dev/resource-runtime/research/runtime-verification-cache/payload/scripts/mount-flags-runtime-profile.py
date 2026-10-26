#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/iokitd-matching-runtime-profile.py'))
def profile(include_system_resources=True):
 p=parent['profile'](include_system_resources);d=json.loads((root/'artifacts/mount-flags-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 assert d['previous_source_runtime']==p['source_runtime']
 for key in ['kernel_build','notifyd_build','mount_flags_header','notifyd_binary']:assert digest(d[key])==d[key+'_sha256']
 verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
 for build in [d['source_kernel'],d['source_notifyd']]:
  for item in build['sources']:verify(item)
  for group in ['headers','source_list_headers','metadata_source_headers']:
   for n,sha in build.get(group,{}).items():verify(dict(source=n,sha256=sha))
 for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
 assert digest(d['variant_root']+'/usr/lib/system/libsystem_kernel.dylib')==d['source_kernel']['binary_sha256']
 return {**p,'source_runtime':d['source_runtime'],'source_mount_flags':d}
def environment(p):return parent['environment'](p)
