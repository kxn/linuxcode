#!/usr/bin/env python3
"""Select one immutable resource-aware xcrun candidate without changing defaults."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(root/'scripts/ios-resource-closure-profile.py'))
base=runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'))
def profile(diagnostic=False,dispatch_stage='artifacts/resource-tool-dispatch-sharing-v1-stage.json',include_resource_environment=False):
 data=json.loads((root/dispatch_stage).read_text());sha=lambda name:hashlib.sha256((root/name).read_bytes()).hexdigest()
 assert sha(data['resource_stage'])==data['resource_stage_sha256']
 p=parent['profile'](diagnostic=diagnostic,stage=data['resource_stage']);chosen=data['runtimes']['diagnostic' if diagnostic else 'normal']
 assert chosen['previous_source_runtime']==p['source_runtime']
 assert chosen['environment']==[arg for arg in p['command'] if arg.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH='))]
 for value in chosen['source_runtime'].values():assert sha(value['path'])==value['sha256']
 for name,digest in chosen['files'].items():assert sha(name)==digest
 assert sha(chosen['system_version_binding'])==chosen['system_version_binding_sha256']
 if 'libdyld_source_build' in chosen:
  build=chosen['libdyld_source_build'];assert sha(build['report'])==build['sha256']
  assert chosen['source_runtime']['LINUXCODE_LIBDYLD']['sha256']==build['library_sha256']
 caller=p if include_resource_environment else base['profile'](diagnostic=diagnostic)
 assert caller['source_runtime']==p['source_runtime']
 if 'fallback_environment' in chosen:
  baseline=base['profile'](diagnostic=diagnostic)
  assert chosen['fallback_environment']==[arg for arg in baseline['command'] if arg.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH='))]
 return {**p,'command':caller['command'],'source_runtime':chosen['source_runtime'],'system_version_binding':chosen['system_version_binding'],
  'resource_environment_applied_to_caller':include_resource_environment,
  'resource_tool_dispatch':data,'resource_tool_dispatch_stage':dispatch_stage,'resource_tool_dispatch_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
