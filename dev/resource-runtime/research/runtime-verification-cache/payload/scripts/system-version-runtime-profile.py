#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent;parent=runpy.run_path(str(root/'scripts/fatal-signal-runtime-profile.py'))
def profile(include_system_resources=True,diagnostic=False):
 p=parent['profile'](include_system_resources,diagnostic);d=json.loads((root/'artifacts/system-version-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 for n,sha in d['original_resources'].items():assert digest(n)==sha,n
 assert digest(d['selected_native_icu'])==d['selected_native_icu_sha256']
 chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['previous_source_runtime']==p['source_runtime']
 for n,sha in chosen['resources'].items():assert digest(n)==sha,n
 for item in chosen['source_runtime'].values():assert digest(item['path'])==item['sha256']
 command=list(p['command']);assert command[4]=='bin/darling';command[4]='bin/darling-system-version'
 binding=next(iter(chosen['resources']))
 return {**p,'command':command,'system_version_binding':binding,'source_runtime':chosen['source_runtime'],'original_system_version':d,'system_version_selected_runtime':chosen}
def environment(p):
 result=parent['environment'](p);result['LINUXCODE_SYSTEM_VERSION']=str(root/p['system_version_binding']);return result
