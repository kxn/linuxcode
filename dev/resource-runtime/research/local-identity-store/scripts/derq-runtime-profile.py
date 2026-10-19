#!/usr/bin/env python3
"""Select original headless derq with the private native identity signing profile."""
from pathlib import Path
import hashlib,json,runpy
r=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(r/'scripts/local-identity-store-profile.py'))
def profile(*,derq_stage,diagnostic=False,**kwargs):
    data=json.loads((r/derq_stage).read_text());sha=lambda n:hashlib.sha256((r/n).read_bytes()).hexdigest()
    assert sha(data['codesign_stage'])==data['codesign_stage_sha256'];assert kwargs['codesign_stage']==data['codesign_stage']
    chosen=data['runtimes']['diagnostic' if diagnostic else 'normal']
    for table in [data['files'],chosen['files']]:
        for n,digest in table.items():assert sha(n)==digest,n
    for value in chosen['source_runtime'].values():assert sha(value['path'])==value['sha256']
    p=parent['profile'](diagnostic=diagnostic,**kwargs);command=list(p['command']);i=next(i for i,v in enumerate(command) if v.startswith('DYLD_LIBRARY_PATH='));command[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/'+data['root']+'/libraries:'+command[i].split('=',1)[1]
    return {**p,'command':command,'source_runtime':chosen['source_runtime'],'system_version_binding':chosen['system_version_binding'],'derq_stage':derq_stage}
def environment(p):return parent['environment'](p)
