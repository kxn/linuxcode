#!/usr/bin/env python3
"""Extend the coherent metadata profile with original ContainerManager exports."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/metadata-kernel-profile.py'))
environment=m['environment']
def profile(kernel_profile=None):
 p=m['profile']() if kernel_profile is None else kernel_profile;stage=json.loads((root/'artifacts/container-manager-export-stage.json').read_text())
 for key in ['base','library','original','provider','client','helper','source','trampolines']:
  assert verified_digest((root/stage[key]))==stage[key+'_sha256']
 c=list(p['command']);index=next(i for i,v in enumerate(c) if v.startswith('DYLD_LIBRARY_PATH='));key,value=c[index].split('=',1)
 c[index]=key+'=/Volumes/SystemRoot/workspace/runtime/container-manager-export/libraries:'+value
 return {**p,'command':c,'container_manager':stage}
