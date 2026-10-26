#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/materialize-runtime-profile.py'))
def profile(include_system_resources=True,diagnostic=False):
 p=parent['profile'](include_system_resources,diagnostic)
 d=json.loads((root/'artifacts/mobileasset-query-build.json').read_text());digest=lambda n:verified_digest((root/n))
 for n,sha in d['source_files'].items():assert digest(n)==sha,n
 assert digest(d['framework'])==d['framework_sha256']
 command=list(p['command']);i=next(i for i,a in enumerate(command) if a.startswith('DYLD_FRAMEWORK_PATH='))
 command[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/mobileasset-query-source/frameworks:'+command[i].split('=',1)[1]
 return {**p,'command':command,'source_mobileasset_query':d}
def environment(p):return parent['environment'](p)
