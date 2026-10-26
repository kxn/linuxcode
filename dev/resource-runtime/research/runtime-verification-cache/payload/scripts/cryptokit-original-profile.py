#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/argument-parser-native-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/cryptokit-original-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    for item in d['images']:
        for key in ['original','source','reconstruction','framework']:assert digest(item[key])==item[key+'_sha256'],key
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_FRAMEWORK_PATH='))
    command[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/cryptokit-original-native/frameworks:'+command[i].split('=',1)[1]
    return {**p,'command':command,'native_original_cryptokit':d}
def environment(p):return m['environment'](p)
