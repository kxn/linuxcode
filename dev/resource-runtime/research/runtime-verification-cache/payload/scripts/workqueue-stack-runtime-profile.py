#!/usr/bin/env python3
"""Select the complete source kernel with the x86_64 workqueue stack repair."""
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/cryptex-native-profile.py'))
verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources)
    name='artifacts/workqueue-stack-kernel-source-build.json'
    build=json.loads((root/name).read_text())
    digest=lambda n:verified_digest((root/n))
    assert build['full_libsystem_kernel_source_build'] and build['complete_source_files']==877
    for item in build['sources']:verify_source(item)
    for n,sha in build['metadata_source_headers'].items():verify_source(dict(source=n,sha256=sha))
    binary='runtime/workqueue-stack-kernel-source/libsystem_kernel.dylib'
    assert digest(binary)==build['binary_sha256']
    assert digest(build['variant_root']+'/usr/lib/system/libsystem_kernel.dylib')==build['binary_sha256']
    stage=json.loads((root/'artifacts/workqueue-stack-runtime-stage.json').read_text())
    assert stage['previous_source_runtime']==p['source_runtime']
    assert stage['kernel_build']==name and stage['kernel_build_sha256']==digest(name)
    selected=stage['source_runtime']
    assert selected['LINUXCODE_LIBSYSTEM_KERNEL']==dict(path=binary,sha256=build['binary_sha256'])
    for key,item in selected.items():
        if key!='LINUXCODE_LIBSYSTEM_KERNEL':assert item['sha256']==p['source_runtime'][key]['sha256']
    for item in selected.values():assert digest(item['path'])==item['sha256']
    return {**p,'source_runtime':selected,'source_workqueue_stack':dict(report=name,sha256=digest(name),previous_source_runtime=p['source_runtime'])}
def environment(p):return m['environment'](p)
