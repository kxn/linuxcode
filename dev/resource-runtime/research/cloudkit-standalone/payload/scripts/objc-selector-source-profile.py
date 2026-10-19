#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
m=runpy.run_path(str(root/'scripts/fsevents-flush-profile.py'));environment=m['environment']
def profile():
 p=m['profile']();stage=json.loads((root/'artifacts/objc-selector-source-stage.json').read_text());digest=lambda n:hashlib.sha256((root/n).read_bytes()).hexdigest()
 for key in ['build_report','library','helper','enumeration_source','base','old_guard_source']:assert digest(stage[key])==stage[key+'_sha256']
 build=json.loads((root/stage['build_report']).read_text())
 for n,sha in build['source_files'].items():resolve('vendor/darling/src/external/objc4/runtime/'+n,sha)
 for n,sha in build['build_inputs'].items():resolve(n,sha)
 c=list(p['command']);i=next(i for i,v in enumerate(c) if v.startswith('DYLD_LIBRARY_PATH='));c[i]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/runtime/objc-selector-source/libraries:/Volumes/SystemRoot/workspace/runtime/objc-selector-source:'+c[i].split('=',1)[1]
 return {**p,'command':c,'source_objc':build,'source_selector':stage}
