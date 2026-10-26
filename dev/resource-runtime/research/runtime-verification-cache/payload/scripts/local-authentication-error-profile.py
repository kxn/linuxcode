#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/crypto-token-kit-native-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/local-authentication-error-source-build.json').read_text());digest=lambda n:verified_digest((root/n))
    assert digest(d['framework'])==d['framework_sha256']
    for item in d['sources']:assert digest(item['source'])==item['sha256']
    for n,sha in d['source_headers'].items():assert digest(n)==sha
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_FRAMEWORK_PATH='));command[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/local-authentication-error-source/frameworks:'+command[i].split('=',1)[1]
    return {**p,'command':command,'source_local_authentication':d}
def environment(p):return m['environment'](p)
