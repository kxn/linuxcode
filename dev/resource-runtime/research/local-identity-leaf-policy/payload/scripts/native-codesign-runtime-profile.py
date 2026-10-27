#!/usr/bin/env python3
"""Use original codesign over the coherent source kernel and real local identities."""
from pathlib import Path
import hashlib,json,os,runpy
r=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(r / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(r/'scripts/resource-tool-dispatch-profile.py'))
def profile(*,native_codesign_stage,identity_store,diagnostic=False):
    sha=lambda n:verified_digest((r/n));data=json.loads((r/native_codesign_stage).read_text())
    resolve=runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve']
    for n,d in {**data['files'],**data['dependency_sha256']}.items():assert sha(n)==d,n
    assert sha(data['persistent_codesign'])==data['persistent_codesign_sha256']
    p=parent['profile'](dispatch_stage=data['dispatch_stage'],diagnostic=diagnostic)
    xattr=json.loads((r/data['xattr_stage']).read_text());chosen=xattr['runtimes']['diagnostic' if diagnostic else 'normal']
    assert sha(xattr['kernel_build'])==xattr['kernel_build_sha256'];assert sha(xattr['derq_stage'])==xattr['derq_stage_sha256']
    derq=json.loads((r/xattr['derq_stage']).read_text());identity=json.loads((r/data['identity_stage']).read_text());closure=json.loads((r/data['closure_stage']).read_text())
    for table in [chosen['files'],derq['files'],identity['files'],closure['files']]:
        for n,d in table.items():resolve(n,d)
    for v in chosen['source_runtime'].values():assert sha(v['path'])==v['sha256']
    for n,target in closure['links'].items():assert os.readlink(r/n)==target,n
    store=(r/identity_store).resolve();store.relative_to(r/'runtime')
    command=list(p['command']);command[4]=data['launcher']
    for prefix,paths in [('DYLD_FRAMEWORK_PATH=',[closure['root']+'/frameworks']),('DYLD_LIBRARY_PATH=',[closure['root']+'/libraries',identity['root']+'/libraries',derq['root']+'/libraries'])]:
        i=next(i for i,v in enumerate(command) if v.startswith(prefix));command[i]=prefix+':'.join('/Volumes/SystemRoot/workspace/'+n for n in paths)+':'+command[i].split('=',1)[1]
    command[-2:-2]=['LINUXCODE_IDENTITY_STORE=/Volumes/SystemRoot/workspace/'+str(store.relative_to(r)),'LINUXCODE_IDENTITY_TRACE=1','LINUXCODE_CODE_SIGNER_TRACE=1']
    return {**p,'command':command,'source_runtime':chosen['source_runtime'],'system_version_binding':chosen['system_version_binding'],'native_codesign_stage':native_codesign_stage,'local_identity_store':str(store.relative_to(r)),'native_codesign':data}
def environment(p):return parent['environment'](p)
