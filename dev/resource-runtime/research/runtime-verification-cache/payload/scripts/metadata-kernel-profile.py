#!/usr/bin/env python3
"""Select a coherent private metadata kernel and unchanged companion libraries."""
from pathlib import Path
import hashlib,json,os,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
digest=lambda p:verified_digest((root/p))
verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
def profile(build_report='artifacts/metadata-kernel-source-build.json',build_dir='runtime/metadata-kernel-source'):
    name='artifacts/uniform-type-identifiers-native-xcode-sysdir-sandbox-container-nounlink-typed-malloc-simple-log-datavault-user-local-dir-source-libtrace-source-objc-support-showsdks.json'
    base=json.loads((root/name).read_text())
    build=json.loads((root/build_report).read_text())
    assert build['full_libsystem_kernel_source_build'] and build['complete_source_files'] in (874,875)
    for path,sha in build['metadata_source_headers'].items():assert digest(path)==sha
    for item in build['sources']:verify_source(item)
    selected={key:dict(item) for key,item in base['source_runtime'].items()}
    for key,filename in [('LINUXCODE_LIBSYSTEM_KERNEL','libsystem_kernel.dylib'),('LINUXCODE_QUARANTINE','libquarantine.dylib'),('LINUXCODE_SANDBOX','libsystem_sandbox.dylib'),('LINUXCODE_LIBDYLD','libdyld.dylib')]:
        path=build_dir+'/'+filename;sha=digest(path)
        if key=='LINUXCODE_LIBSYSTEM_KERNEL':assert sha==build['binary_sha256']
        else:assert sha==selected[key]['sha256']
        assert digest(build_dir+'/darling-root/usr/lib/system/'+filename)==sha
        selected[key]=dict(path=path,sha256=sha)
    for item in selected.values():assert digest(item['path'])==item['sha256']
    return dict(command=list(base['command']),source_runtime=selected,source_kernel=build,base_profile=name,base_profile_sha256=digest(name))
def environment(value):
    result=os.environ.copy();result.update({k:str(root/v['path']) for k,v in value['source_runtime'].items()});return result
