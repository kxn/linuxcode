#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/xpc-sent-message-runtime-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/applearchive-native-stage.json').read_text());digest=lambda n:verified_digest((root/n))
    for n,sha in d['files'].items():assert digest(n)==sha,n
    for image in d['images']:
        for key in ['original','source','reconstruction']:assert digest(image[key])==image[key+'_sha256']
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_LIBRARY_PATH='))
    command[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/'+d['libraries']+':'+command[i].split('=',1)[1]
    return {**p,'command':command,'native_applearchive':d}
def environment(p):return m['environment'](p)
