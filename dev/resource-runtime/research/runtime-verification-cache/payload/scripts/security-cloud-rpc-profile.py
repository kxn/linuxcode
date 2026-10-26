#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/mdns-native-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources)
    stage=json.loads((root/'artifacts/security-cloud-rpc-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    for name in ['base','library','provider']:assert digest(stage[name])==stage[name+'_sha256']
    for name,sha in {**stage['build']['sources'],**stage['build']['generated_headers']}.items():assert digest(name)==sha
    c=list(p['command'])
    for key,folder in [('DYLD_LIBRARY_PATH','libraries'),('DYLD_FRAMEWORK_PATH','frameworks')]:
        i=next(i for i,a in enumerate(c) if a.startswith(key+'='));c[i]=key+'=/Volumes/SystemRoot/workspace/runtime/security-cloud-rpc-stage/'+folder+':'+c[i].split('=',1)[1]
    return {**p,'command':c,'source_security_cloud_rpc':stage}
def environment(p):return m['environment'](p)
