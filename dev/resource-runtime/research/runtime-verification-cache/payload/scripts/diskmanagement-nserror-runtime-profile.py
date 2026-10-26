#!/usr/bin/env python3
"""Add the complete source DiskManagement framework to the workloop runtime."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/dispatch-workloop-runtime-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);name='artifacts/diskmanagement-nserror-source-build.json'
    build=json.loads((root/name).read_text());digest=lambda n:verified_digest((root/n))
    assert build['full_framework_source_build'] and build['complete_source_files']==23 and build['complete_DMNSError_instructions_identical_to_native']
    for n,sha in build['source_files'].items():assert digest(n)==sha,n
    assert digest(build['framework'])==build['framework_sha256']
    assert digest(build['reference'])==build['reference_sha256']
    command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_FRAMEWORK_PATH='))
    command[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/diskmanagement-nserror-source/frameworks:'+command[i].split('=',1)[1]
    return {**p,'command':command,'source_diskmanagement_nserror':build}
def environment(p):return m['environment'](p)
