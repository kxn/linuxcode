#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/combine-native-profile.py'));environment=m['environment']
def profile():
 p=m['profile']();report=(root/os.environ.get('LINUXCODE_FSEVENTS_BUILD_REPORT','artifacts/fsevents-flush-source-build.json')).resolve();assert report.is_relative_to(root/'artifacts')
 stage=json.loads(report.read_text());digest=lambda n:verified_digest((root/n))
 resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
 for key in ['original','library']:assert digest(stage[key])==stage[key+'_sha256']
 for n,sha in {**stage['sources'],**stage['headers']}.items():assert digest(resolve(n,sha))==sha
 frameworks=str(Path(stage['library']).parents[3]);c=list(p['command']);i=next(i for i,v in enumerate(c) if v.startswith('DYLD_FRAMEWORK_PATH='));c[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/'+frameworks+':'+c[i].split('=',1)[1]
 return {**p,'command':c,'source_fsevents':stage}
