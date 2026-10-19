#!/usr/bin/env python3
"""Opt-in native identities for the existing private headless signing profile."""
from pathlib import Path
import hashlib,json,runpy
r=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(r/'scripts/codesign-zsign-runtime-profile.py'))
def profile(*,identity_stage,identity_store,codesign_stage,diagnostic=False,trace=False):
    data=json.loads((r/identity_stage).read_text())
    for name,digest in data['files'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==digest,name
    store=(r/identity_store).resolve();store.relative_to(r/'runtime')
    p=parent['profile'](codesign_stage=codesign_stage,diagnostic=diagnostic);command=list(p['command'])
    for prefix,leaf in [('DYLD_FRAMEWORK_PATH=','frameworks'),('DYLD_LIBRARY_PATH=','libraries')]:
        i=next(i for i,v in enumerate(command) if v.startswith(prefix));command[i]=prefix+'/Volumes/SystemRoot/workspace/'+data['root']+'/'+leaf+':'+command[i].split('=',1)[1]
    command[-2:-2]=['LINUXCODE_IDENTITY_STORE=/Volumes/SystemRoot/workspace/'+str(store.relative_to(r))]+(['LINUXCODE_IDENTITY_TRACE=1'] if trace else [])
    return {**p,'command':command,'local_identity_stage':identity_stage,'local_identity_store':str(store.relative_to(r))}
def environment(p):return parent['environment'](p)
