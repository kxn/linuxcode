#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/sandbox-policy-source-profile.py'))
verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources)
    stage=json.loads((root/'artifacts/pid-generation-vfs-baseline-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    assert stage['previous_source_runtime']==p['source_runtime']
    assert digest(stage['kernel_build_report'])==stage['kernel_build_report_sha256']
    build=json.loads((root/stage['kernel_build_report']).read_text())
    for item in build['sources']:verify_source(item)
    for name,sha in {**build['metadata_source_headers'],**stage['source_files']}.items():assert digest(name)==sha
    for item in stage['source_runtime'].values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':stage['source_runtime'],'source_pid_generation':stage}
def environment(p):return m['environment'](p)
