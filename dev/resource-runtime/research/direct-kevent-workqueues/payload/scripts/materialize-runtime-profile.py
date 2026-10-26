#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
parent=runpy.run_path(str(root/'scripts/xpc-activation-runtime-profile.py'))
def profile(include_system_resources=True,diagnostic=False):
 p=parent['profile'](include_system_resources,diagnostic);d=json.loads((root/'artifacts/materialize-policy-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 assert digest(d['kernel_build'])==d['kernel_build_sha256']
 resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
 resolve(d['tsd_header'],d['tsd_header_sha256'])
 verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
 for item in d['source_kernel']['sources']:verify(item)
 for n,sha in d['source_kernel']['metadata_source_headers'].items():verify(dict(source=n,sha256=sha))
 chosen=d['runtimes']['diagnostic' if diagnostic else 'normal'];assert chosen['previous_source_runtime']==p['source_runtime'] and chosen['test_only_permissive_coreservices_policy']==diagnostic
 for v in chosen['source_runtime'].values():assert digest(v['path'])==v['sha256']
 assert digest(chosen['policy'])==chosen['policy_sha256']
 return {**p,'source_runtime':chosen['source_runtime'],'source_materialize_policy':d,'materialize_selected_runtime':chosen}
def environment(p):return parent['environment'](p)
