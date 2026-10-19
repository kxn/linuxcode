#!/usr/bin/env python3
"""Select a verified private codesign namespace with a real Linux signing backend."""
from pathlib import Path
import hashlib,json,runpy
r=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(r/'scripts/resource-tool-dispatch-profile.py'))
def profile(*,codesign_stage,diagnostic=False):
 data=json.loads((r/codesign_stage).read_text());sha=lambda name:hashlib.sha256((r/name).read_bytes()).hexdigest()
 assert sha(data['dispatch_stage'])==data['dispatch_stage_sha256']
 assert sha(data['zsign_build'])==data['zsign_build_sha256']
 for table in ['files','ruby_gem_files']:
  for name,digest in data[table].items():assert sha(name)==digest,name
 assert sha(data['original_persistent_codesign'])==data['original_persistent_codesign_sha256']
 p=parent['profile'](diagnostic=diagnostic,dispatch_stage=data['dispatch_stage']);command=list(p['command']);assert command[4]=='bin/darling-system-version';command[4]=data['launcher']
 return {**p,'command':command,'source_codesign_adapter':data,'codesign_adapter_stage':codesign_stage}
def environment(p):return parent['environment'](p)
