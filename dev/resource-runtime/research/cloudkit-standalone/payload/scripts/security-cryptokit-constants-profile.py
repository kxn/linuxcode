#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/crypto-token-parameters-profile.py'))
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/security-cryptokit-constants-source-build.json').read_text());digest=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest()
    for key in ['source','source_list']:resolve(d[key],d[key+'_sha256'])
    for key in ['library','framework','base','reference']:assert digest(d[key])==d[key+'_sha256'],key
    command=list(p['command'])
    for variable,directory in [('DYLD_FRAMEWORK_PATH','frameworks'),('DYLD_LIBRARY_PATH','libraries')]:
        i=next(i for i,a in enumerate(command) if a.startswith(variable+'='));command[i]=variable+'=/Volumes/SystemRoot/workspace/runtime/security-cryptokit-constants/'+directory+':'+command[i].split('=',1)[1]
    return {**p,'command':command,'source_security_cryptokit_constants':d}
def environment(p):return m['environment'](p)
