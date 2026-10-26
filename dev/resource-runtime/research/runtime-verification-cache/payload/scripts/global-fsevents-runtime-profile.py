#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/corpse-map-runtime-profile.py'))
def profile(diagnostic=False):
    p=parent['profile'](diagnostic=diagnostic)
    d=json.loads((root/'artifacts/global-fsevents-stage.json').read_text());digest=lambda n:verified_digest((root/n))
    assert digest(d['server_build'])==d['server_build_sha256']
    chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['previous_source_runtime']==p['source_runtime']
    for item in chosen['source_runtime'].values():assert digest(item['path'])==item['sha256']
    assert digest(chosen['system_version_binding'])==chosen['system_version_binding_sha256']
    component=json.loads((root/'artifacts/global-fsevents-source-build.json').read_text())
    assert digest(component['library'])==component['library_sha256']
    for name,sha in {**component['sources'],**component['headers']}.items():assert digest(name)==sha,name
    command=list(p['command']);index=next(i for i,value in enumerate(command) if value.startswith('DYLD_FRAMEWORK_PATH='))
    command[index]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/global-fsevents-source/frameworks:'+command[index].split('=',1)[1]
    return {**p,'command':command,'source_global_fsevents_framework':component,'source_runtime':chosen['source_runtime'],'system_version_binding':chosen['system_version_binding'],
            'source_global_fsevents':d,'global_fsevents_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
