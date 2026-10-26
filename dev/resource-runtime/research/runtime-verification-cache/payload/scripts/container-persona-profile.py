#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/log-hooks-profile.py'));environment=m['environment']
def profile():
 p=m['profile']();stage=json.loads((root/'artifacts/container-persona-stage.json').read_text())
 for key in ['base','library','helper','source','original','provider']:assert verified_digest((root/stage[key]))==stage[key+'_sha256']
 c=list(p['command']);i=next(i for i,v in enumerate(c) if v.startswith('DYLD_LIBRARY_PATH='));c[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/container-persona/libraries:'+c[i].split('=',1)[1]
 return {**p,'command':c,'container_persona':stage}
