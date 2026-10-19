#!/usr/bin/env python3
"""Select the complete libdispatch source build with scoped fallback workloops."""
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
m=runpy.run_path(str(root/'scripts/workqueue-stack-runtime-profile.py'))
def profile(include_system_resources=True):
    p=m['profile'](include_system_resources);name='artifacts/dispatch-workloop-source-build.json'
    build=json.loads((root/name).read_text());digest=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest()
    assert build['full_libdispatch_source_build'] and build['complete_source_files']==32
    resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
    for item in build['sources']:resolve(item['source'],item['sha256'])
    for n,sha in build['source_headers'].items():resolve(n,sha)
    assert digest(build['library'])==build['library_sha256']
    assert digest(build['variant_root']+'/usr/lib/system/libdispatch.dylib')==build['library_sha256']
    assert build['previous_source_runtime']==p['source_runtime']
    for key,item in build['source_runtime'].items():
        assert digest(item['path'])==item['sha256']==p['source_runtime'][key]['sha256']
    return {**p,'source_runtime':build['source_runtime'],'source_dispatch_workloop':dict(report=name,sha256=digest(name),library=build['library'],library_sha256=build['library_sha256'])}
def environment(p):return m['environment'](p)
