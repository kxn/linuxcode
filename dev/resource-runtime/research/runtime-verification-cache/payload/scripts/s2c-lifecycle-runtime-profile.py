#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(root/'scripts/mount-flags-runtime-profile.py'))
def profile(include_system_resources=True,diagnostic=False):
 p=parent['profile'](include_system_resources);d=json.loads((root/'artifacts/s2c-lifecycle-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 assert d['previous_source_runtime']==p['source_runtime'] and digest(d['server_build'])==d['server_build_sha256']
 resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
 for n,sha in d['source_server']['source_files'].items():assert digest(resolve(n,sha))==sha,n
 chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['test_only_permissive_coreservices_policy']==diagnostic
 for v in chosen['source_runtime'].values():assert digest(v['path'])==v['sha256']
 assert digest(chosen['policy'])==chosen['policy_sha256']
 return {**p,'source_runtime':chosen['source_runtime'],'source_s2c_lifecycle':d,'s2c_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
