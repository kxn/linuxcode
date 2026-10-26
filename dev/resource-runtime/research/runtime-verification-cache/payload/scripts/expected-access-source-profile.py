#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/sandbox-check-source-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);stage=json.loads((root/'artifacts/expected-access-source-build.json').read_text())
    digest=lambda n:verified_digest((root/n))
    for name in ['library','base','baseline','unprocessed']:assert digest(stage[name])==stage[name+'_sha256']
    for name,sha in {**stage['source_files'],**stage['existing_object_inputs']}.items():assert digest(name)==sha
    c=list(p['command']);i=next(i for i,a in enumerate(c) if a.startswith('DYLD_LIBRARY_PATH='));c[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/expected-access-source/libraries:'+c[i].split('=',1)[1]
    return {**p,'command':c,'source_expected_access':stage}
def environment(p):return m['environment'](p)
