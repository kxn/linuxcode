#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/mobile-device-native-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);stage=json.loads((root/'artifacts/crypto-quarantine-runtime-stage.json').read_text())
    digest=lambda n:verified_digest((root/n))
    assert stage['previous_source_runtime']==p['source_runtime']
    for name in ['coreutils_build','native','native_provider','native_reconstruction']:assert digest(stage[name])==stage[name+'_sha256']
    for name,sha in stage['quarantine_source_files'].items():assert digest(name)==sha
    for name,sha in stage['bootstrap_helpers'].items():assert digest(name)==sha
    crypto=json.loads((root/stage['coreutils_build']).read_text())
    for name,sha in crypto['source_headers'].items():assert digest(name)==sha
    for item in crypto['sources']:
        assert digest(item['source'])==item['sha256'];assert digest(item['object'])==item['object_sha256']
    assert digest(crypto['library'])==crypto['library_sha256']
    for item in stage['source_runtime'].values():assert digest(item['path'])==item['sha256']
    command=list(p['command'])
    for key,folder in [('DYLD_FRAMEWORK_PATH','runtime/coreutils-crypto-source/frameworks'),('DYLD_LIBRARY_PATH','runtime/crypto-quarantine-runtime/libraries')]:
        at=next(i for i,arg in enumerate(command) if arg.startswith(key+'='));command[at]=key+'=/Volumes/SystemRoot/workspace/'+folder+':'+command[at].split('=',1)[1]
    return {**p,'source_runtime':stage['source_runtime'],'command':command,'source_crypto_quarantine':stage,'source_coreutils_crypto':crypto}
def environment(p):return m['environment'](p)
