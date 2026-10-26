#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/corecrypto-original-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/crypto-token-parameters-source-build.json').read_text());digest=lambda n:verified_digest((root/n))
    for key in ['source','source_list','library','framework','base','reference']:assert digest(d[key])==d[key+'_sha256'],key
    command=list(p['command'])
    for variable,directory in [('DYLD_FRAMEWORK_PATH','frameworks'),('DYLD_LIBRARY_PATH','libraries')]:
        i=next(i for i,a in enumerate(command) if a.startswith(variable+'='));command[i]=variable+'=/Volumes/SystemRoot/workspace/runtime/crypto-token-parameters-source/'+directory+':'+command[i].split('=',1)[1]
    return {**p,'command':command,'source_token_parameters':d}
def environment(p):return m['environment'](p)
