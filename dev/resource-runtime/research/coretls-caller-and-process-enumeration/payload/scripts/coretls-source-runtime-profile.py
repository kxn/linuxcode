"""Select one complete source CoreTLS backend and matching umbrella per process."""
from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent.parent
def select(profile,report):
    build=json.loads((r/report).read_text());assert build['full_coretls_source_build'] and build['complete_source_files']==31
    for key in ['backend','umbrella','corecrypto','private_corecrypto']:assert hashlib.sha256((r/build[key]).read_bytes()).hexdigest()==build[key+'_sha256']
    assert build['global_CoreCrypto_replaced'] is False
    paths=[(r/build['backend']).parent]
    prefix=':'.join('/Volumes/SystemRoot/workspace/'+str(p.relative_to(r)) for p in paths)+':'
    command=list(profile['command']);index=next(i for i,v in enumerate(command) if v.startswith('DYLD_LIBRARY_PATH='));command[index]='DYLD_LIBRARY_PATH='+prefix+command[index].split('=',1)[1]
    direct=dict(profile['direct_resource_environment']);scope=dict(direct['tool_environment']);scope['DYLD_LIBRARY_PATH']=prefix+scope['DYLD_LIBRARY_PATH'];direct['tool_environment']=scope
    return {**profile,'command':command,'direct_resource_environment':direct,'source_coretls_build':report}
