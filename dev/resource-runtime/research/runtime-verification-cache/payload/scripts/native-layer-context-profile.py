#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/native-layer-profile.py'))
environment=m['environment']
def profile():
 p=m['profile']();stage=json.loads((root/'artifacts/native-layer-context-stage.json').read_text())
 for key in ['base','library','helper','source','header']:assert verified_digest((root/stage[key]))==stage[key+'_sha256']
 c=list(p['command'])
 for key,folder in [('DYLD_FRAMEWORK_PATH','frameworks'),('DYLD_LIBRARY_PATH','libraries')]:
  i=next(i for i,v in enumerate(c) if v.startswith(key+'='));c[i]=key+'=/Volumes/SystemRoot/workspace/runtime/native-layer-context/'+folder+':'+c[i].split('=',1)[1]
 return {**p,'command':c,'native_layer_context':stage}
