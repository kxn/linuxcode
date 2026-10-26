#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/native-layer-context-profile.py'))
environment=m['environment']
def profile(source_build=None):
 p=m['profile']();stage=json.loads((root/'artifacts/log-enablement-stage.json').read_text());build=stage['source_build'] if source_build is None else source_build
 for key in ['base','library']:assert verified_digest((root/stage[key]))==stage[key+'_sha256']
 assert verified_digest((root/build['library']))==build['library_sha256']
 verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
 for path,sha in {**build['source_files'],**build['source_headers']}.items():
  verify(dict(source='vendor/darling/src/external/libtrace/'+path,sha256=sha))
 c=list(p['command']);i=next(i for i,v in enumerate(c) if v.startswith('DYLD_LIBRARY_PATH='))
 folder=str(Path(build['library']).parent)
 c[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/log-enablement/libraries:/Volumes/SystemRoot/workspace/'+folder+':'+c[i].split('=',1)[1]
 return {**p,'command':c,'log_enablement':stage,**({'libtrace_source_override':build} if source_build else {})}
