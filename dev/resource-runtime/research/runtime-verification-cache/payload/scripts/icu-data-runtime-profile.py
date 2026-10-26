#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent;parent=runpy.run_path(str(root/'scripts/mobileasset-query-runtime-profile.py'))
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
def profile(include_system_resources=True,diagnostic=False):
 p=parent['profile'](include_system_resources,diagnostic);d=json.loads((root/'artifacts/icu-data-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 for n,sha in d['original_resources'].items():assert digest(n)==sha,n
 assert digest(d['selected_native_icu'])==d['selected_native_icu_sha256']
 chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['previous_source_runtime']==p['source_runtime']
 for n,sha in chosen['resources'].items():assert digest(n)==sha,n
 for item in chosen['source_runtime'].values():assert digest(item['path'])==item['sha256']
 return {**p,'source_runtime':chosen['source_runtime'],'original_icu_data':d,'icu_data_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
