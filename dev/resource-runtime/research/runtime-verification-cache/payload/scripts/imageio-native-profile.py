#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,runpy
root=Path(__file__).resolve().parent.parent
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
m=runpy.run_path(str(root/'scripts/runnable-archs-profile.py'));environment=m['environment']
def profile():
 p=m['profile']();stage=json.loads((root/'artifacts/imageio-native-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 for e in stage['entries']:
  for key in ['original','source','library','reconstruction']:assert digest(e[key])==e[key+'_sha256']
 for key in ['source','library']:assert digest(stage['typed_cpp_adapter'][key])==stage['typed_cpp_adapter'][key+'_sha256']
 constants=json.loads((root/'artifacts/imageio-cg-constants-stage.json').read_text())
 for key in ['base','source','helper','library','analysis']:assert digest(constants[key])==constants[key+'_sha256']
 matrix=json.loads((root/'artifacts/simd-matrix-source-stage.json').read_text())
 for key in ['base','source','helper','library']:assert digest(matrix[key])==matrix[key+'_sha256']
 legacy=json.loads((root/'artifacts/imageio-legacy-key-stage.json').read_text())
 for key in ['base','source','helper','library']:assert digest(legacy[key])==legacy[key+'_sha256']
 c=list(p['command'])
 for key,extra in [('DYLD_LIBRARY_PATH','/Volumes/SystemRoot/workspace/runtime/imageio-legacy-key/libraries:/Volumes/SystemRoot/workspace/runtime/simd-matrix-source/libraries:/Volumes/SystemRoot/workspace/runtime/imageio-cg-constants/libraries:/Volumes/SystemRoot/workspace/runtime/imageio-native/libraries'),('DYLD_FRAMEWORK_PATH','/Volumes/SystemRoot/workspace/runtime/imageio-legacy-key/frameworks:/Volumes/SystemRoot/workspace/runtime/imageio-cg-constants/frameworks:/Volumes/SystemRoot/workspace/runtime/imageio-native/frameworks')]:
  i=next(i for i,v in enumerate(c) if v.startswith(key+'='));c[i]=key+'='+extra+':'+c[i].split('=',1)[1]
 return {**p,'command':c,'imageio_native':stage,'imageio_cg_constants':constants,'simd_matrix':matrix,'imageio_legacy_key':legacy}
