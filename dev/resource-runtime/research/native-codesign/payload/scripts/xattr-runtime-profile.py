#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
r=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(r/'scripts/derq-runtime-profile.py'))
def profile(*,xattr_stage,diagnostic=False,**kwargs):
    data=json.loads((r/xattr_stage).read_text());sha=lambda n:hashlib.sha256((r/n).read_bytes()).hexdigest()
    assert kwargs['derq_stage']==data['derq_stage'];assert sha(data['derq_stage'])==data['derq_stage_sha256'];assert sha(data['kernel_build'])==data['kernel_build_sha256']
    chosen=data['runtimes']['diagnostic' if diagnostic else 'normal']
    for n,d in chosen['files'].items():assert sha(n)==d,n
    for v in chosen['source_runtime'].values():assert sha(v['path'])==v['sha256']
    p=parent['profile'](diagnostic=diagnostic,**kwargs)
    return {**p,'source_runtime':chosen['source_runtime'],'system_version_binding':chosen['system_version_binding'],'xattr_stage':xattr_stage}
def environment(p):return parent['environment'](p)
