#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/applearchive-native-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);d=json.loads((root/'artifacts/corecrypto-hkdf-source-build.json').read_text())
    digest=lambda n:verified_digest((root/n))
    for n,sha in {d['library']:d['library_sha256'],**d['source_headers']}.items():assert digest(n)==sha,n
    for item in d['sources']:assert digest(item['source'])==item['sha256'],item['source']
    if 'BoringSSL' in d:
        b=d['BoringSSL'];assert digest(b['archive'])==b['archive_sha256']
        for n,sha in b['sources'].items():assert digest(n)==sha,n
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_LIBRARY_PATH='))
    command[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/'+str(Path(d['library']).parent)+':'+command[i].split('=',1)[1]
    return {**p,'command':command,'source_corecrypto_hkdf':d}
def environment(p):return m['environment'](p)
