#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/fsevents-device-runtime-profile.py'))
def profile(include_system_resources=True,diagnostic=False):
    p=parent['profile'](include_system_resources,diagnostic=diagnostic)
    d=json.loads((root/('artifacts/log-compose-'+('diagnostic' if diagnostic else 'runtime')+'-stage.json')).read_text())
    digest=lambda n:verified_digest((root/n))
    assert d['previous_source_runtime']==p['source_runtime'] and d['original_policy_override']==diagnostic
    for key in ['source_build','compatibility_source','compatibility_library']:assert digest(d[key])==d[key+'_sha256']
    for name,sha in {**d['source_libtrace']['source_files'],**d['source_libtrace']['source_headers']}.items():
        assert digest('vendor/darling/src/external/libtrace/'+name)==sha,name
    for item in d['source_runtime'].values():assert digest(item['path'])==item['sha256']
    command=list(p['command']);at=next(i for i,v in enumerate(command) if v.startswith('DYLD_LIBRARY_PATH='))
    command[at]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/'+d['library_directory']+':'+command[at].split('=',1)[1]
    return {**p,'command':command,'source_runtime':d['source_runtime'],'source_libtrace':d['source_libtrace'],
            'source_log_compose':d,'coreservices_diagnostic_policy':d['diagnostic_policy']}
def environment(p):return parent['environment'](p)
