"""Select one complete source CoreTLS backend and matching umbrella per process."""
from pathlib import Path
import hashlib,json,runpy
r=Path(__file__).resolve().parent.parent
def select(profile,report):
    build=json.loads((r/report).read_text());assert build['full_coretls_source_build'] and build['complete_source_files']==31
    for key in ['backend','umbrella','corecrypto','private_corecrypto']:assert hashlib.sha256((r/build[key]).read_bytes()).hexdigest()==build[key+'_sha256']
    assert build['global_CoreCrypto_replaced'] is False
    paths=[(r/build['backend']).parent]
    directories=['/Volumes/SystemRoot/workspace/'+str(p.relative_to(r)) for p in paths]
    selected=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'))['prepend_library_directories'](profile,directories)
    return {**selected,'source_coretls_build':report}
