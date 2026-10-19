#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
parent=runpy.run_path(str(root/'scripts/s2c-lifecycle-runtime-profile.py'))
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
def profile(include_system_resources=True,diagnostic=False):
 p=parent['profile'](include_system_resources,diagnostic);d=json.loads((root/'artifacts/xpc-activation-stage.json').read_text());digest=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest()
 assert digest(d['source_build'])==d['source_build_sha256']
 for n,sha in {**d['source_libxpc']['source_files'],**d['source_libxpc']['modified_files']}.items():resolve('vendor/darling/src/external/libxpc/'+n,sha)
 for n,sha in d['source_headers'].items():resolve(n,sha)
 chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['previous_source_runtime']==p['source_runtime']
 assert chosen['test_only_permissive_coreservices_policy']==diagnostic and digest(chosen['policy'])==chosen['policy_sha256']
 for v in chosen['source_runtime'].values():assert digest(v['path'])==v['sha256']
 return {**p,'source_runtime':chosen['source_runtime'],'source_xpc_activation':d,'xpc_activation_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
