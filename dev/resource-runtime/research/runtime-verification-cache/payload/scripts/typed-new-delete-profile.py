#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/security-cloud-rpc-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources)
    stage=json.loads((root/'artifacts/typed-new-delete-source-build.json').read_text())
    digest=lambda n:verified_digest((root/n))
    for name in ['base','library','source','cmake','backend','baseline_relink']:assert digest(stage[name])==stage[name+'_sha256']
    for name,sha in stage['old_object_inputs'].items():assert digest(name)==sha
    c=list(p['command']);i=next(i for i,a in enumerate(c) if a.startswith('DYLD_LIBRARY_PATH='))
    c[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/typed-new-delete-source/libraries:'+c[i].split('=',1)[1]
    return {**p,'command':c,'source_typed_new_delete':stage}
def environment(p):return m['environment'](p)
