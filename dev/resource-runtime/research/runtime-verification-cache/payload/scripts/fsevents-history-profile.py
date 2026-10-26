#!/usr/bin/env python3
"""Select the complete recursive/history-loss source FSEvents component."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/swb-swift-logging-runtime-profile.py'))
def profile(baseline=False,diagnostic=False):
    p=parent['profile'](diagnostic=diagnostic)
    if baseline:return p
    stage=json.loads((root/'artifacts/fsevents-history-source-build.json').read_text())
    digest=lambda name:verified_digest((root/name))
    resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
    for name,sha in {**stage['sources'],**stage['headers']}.items():assert digest(resolve(name,sha))==sha,name
    assert digest(stage['library'])==stage['library_sha256']
    frameworks=str(Path(stage['library']).parents[3])
    command=list(p['command'])
    index=next(i for i,item in enumerate(command) if item.startswith('DYLD_FRAMEWORK_PATH='))
    command[index]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/'+frameworks+':'+command[index].split('=',1)[1]
    return {**p,'command':command,'source_recursive_history_fsevents':stage}
def environment(p):return parent['environment'](p)
