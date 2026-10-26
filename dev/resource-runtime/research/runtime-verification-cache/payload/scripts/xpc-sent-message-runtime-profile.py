#!/usr/bin/env python3
from pathlib import Path
verified_digest = __import__('runpy').run_path(str(Path(__file__).resolve().with_name('verified-file-digest.py')))['digest']
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/diskmanagement-nserror-runtime-profile.py'))
verify_source=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);digest=lambda n:verified_digest((root/n))
    stage=json.loads((root/'artifacts/xpc-sent-message-runtime-stage.json').read_text())
    assert stage['previous_source_runtime']==p['source_runtime'] and digest(stage['build'])==stage['build_sha256']
    build=json.loads((root/stage['build']).read_text());assert build['full_libxpc_source_build']
    for name,sha in {**build['source_files'],**build['modified_files']}.items():verify_source(dict(source='vendor/darling/src/external/libxpc/'+name,sha256=sha))
    assert digest(build['variant_root']+'/usr/lib/system/libxpc.dylib')==build['library_sha256']
    assert digest(build['variant_root']+'/usr/lib/system/libdispatch.dylib')==p['source_dispatch_workloop']['library_sha256']
    for key,item in stage['source_runtime'].items():
        assert digest(item['path'])==item['sha256']
        if key!='LINUXCODE_LIBXPC':assert item['sha256']==p['source_runtime'][key]['sha256']
    return {**p,'source_runtime':stage['source_runtime'],'source_xpc_sent_message':stage}
def environment(p):return m['environment'](p)
