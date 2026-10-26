#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/imageio-native-profile.py'));environment=m['environment']
def profile():
 p=m['profile']();stage=json.loads((root/'artifacts/combine-native-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 for key in ['original','source','library','reconstruction']:assert digest(stage[key])==stage[key+'_sha256']
 c=list(p['command']);i=next(i for i,v in enumerate(c) if v.startswith('DYLD_FRAMEWORK_PATH='));c[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/combine-native/frameworks:'+c[i].split('=',1)[1]
 return {**p,'command':c,'combine_native':stage}
