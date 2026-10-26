#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/security-cryptokit-constants-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/crypto-token-kit-native-stage.json').read_text());digest=lambda n:verified_digest((root/n))
    for key in ['original','source','reconstruction','framework']:assert digest(d[key])==d[key+'_sha256'],key
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_FRAMEWORK_PATH='));command[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/crypto-token-kit-native/frameworks:'+command[i].split('=',1)[1]
    return {**p,'command':command,'native_crypto_token_kit':d}
def environment(p):return m['environment'](p)
