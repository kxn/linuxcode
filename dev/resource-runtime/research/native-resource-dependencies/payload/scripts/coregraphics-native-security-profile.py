#!/usr/bin/env python3
"""Select existing native signing compatibility exports for the resource experiment."""
from pathlib import Path
import hashlib
import json
import os
import runpy

root=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']

def profile(stage='artifacts/ios-resource-lazy-v1-stage.json',
            graphics_stage='artifacts/coregraphics-native-v32-stage.json',
            include_resource_environment=True):
    p=parent['profile'](stage=stage,graphics_stage=graphics_stage,
                        include_resource_environment=include_resource_environment)
    reports=['artifacts/original-codesign-closure-native-local-signer-v1-stage.json',
             'artifacts/local-identity-store-readonly-v2-stage.json']
    data=[]
    for name in reports:
        item=json.loads((root/name).read_text())
        for path,expected in item['files'].items():
            if path.startswith(('scripts/','config/','vendor/')):resolve(path,expected)
            else:assert hashlib.sha256((root/path).read_bytes()).hexdigest()==expected,path
        for path,target in item.get('links',{}).items():assert os.readlink(root/path)==target,path
        data.append(item)
    command=list(p['command'])
    for prefix,paths in [('DYLD_FRAMEWORK_PATH=',[data[0]['root']+'/frameworks']),
                         ('DYLD_LIBRARY_PATH=',[data[0]['root']+'/libraries',data[1]['root']+'/libraries'])]:
        index=next(i for i,v in enumerate(command) if v.startswith(prefix))
        command[index]=prefix+':'.join('/Volumes/SystemRoot/workspace/'+path for path in paths)+':'+command[index].split('=',1)[1]
    store='runtime/local-identity-xcode-empty-v1/store.plist'
    assert (root/store).is_file()
    command[-2:-2]=['LINUXCODE_IDENTITY_STORE=/Volumes/SystemRoot/workspace/'+store]
    return {**p,'command':command,'source_resource_security':dict(reports=reports,
        report_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in reports},
        identity_store=store,identity_store_sha256=hashlib.sha256((root/store).read_bytes()).hexdigest(),
        signing_with_this_resource_profile_verified=False)}

def environment(p):return parent['environment'](p)
