#!/usr/bin/env python3
"""Select source color-space name APIs over the private original-resource closure."""
from pathlib import Path
import hashlib,json,runpy
r=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(r/'scripts/ios-resource-closure-profile.py'))
def profile(stage='artifacts/ios-resource-io80211-v1-stage.json',graphics_stage='artifacts/cg-colorspace-names-v2-stage.json',include_resource_environment=True):
 p=parent['profile'](stage=stage);data=json.loads((r/graphics_stage).read_text())
 for name,digest in data['files'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==digest,name
 caller=p if include_resource_environment else runpy.run_path(str(r/'scripts/xcode-tool-dispatch-runtime-profile.py'))['profile']()
 command=list(caller['command']);folder=str(Path(data['library']).parents[4])
 for prefix,leaf in [('DYLD_FRAMEWORK_PATH=','frameworks'),('DYLD_LIBRARY_PATH=','libraries')]:
  i=next(i for i,v in enumerate(command) if v.startswith(prefix));command[i]=prefix+'/Volumes/SystemRoot/workspace/'+folder+'/'+leaf+':'+command[i].split('=',1)[1]
 return {**p,'command':command,'source_cg_colorspace_names':data,'cg_colorspace_names_stage':graphics_stage}
def environment(p):return parent['environment'](p)
