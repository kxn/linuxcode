#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,runpy
root=Path(__file__).resolve().parent.parent;m=runpy.run_path(str(root/'scripts/device-identity-native-profile.py'))
verified_digest = __import__('runpy').run_path(str(root / 'scripts/verified-file-digest.py'))['digest']
def profile(include_system_resources=True):
 p=m['profile'](include_system_resources);stage=json.loads((root/'artifacts/cryptex-native-stage.json').read_text());digest=lambda n:verified_digest((root/n))
 for n,sha in stage['files'].items():assert digest(n)==sha,n
 for n,target in stage['symlinks'].items():assert os.readlink(root/n)==target
 for image in stage['images']:
  for key in ['original','source','reconstruction']:assert digest(image[key])==image[key+'_sha256']
 attributes=json.loads((root/'artifacts/mobileasset-download-attributes-build.json').read_text())
 assert digest(attributes['framework'])==attributes['framework_sha256']
 verify=runpy.run_path(str(root/'scripts/verify-historical-source.py'))['verify']
 for n,sha in attributes['source_files'].items():verify(dict(source=n,sha256=sha))
 assert digest(attributes['native_attribute_reference'])==attributes['native_attribute_reference_sha256']
 command=list(p['command'])
 for key,folder in [('DYLD_LIBRARY_PATH','libraries'),('DYLD_FRAMEWORK_PATH','frameworks')]:
  i=next(i for i,a in enumerate(command) if a.startswith(key+'='));command[i]=key+'=/Volumes/SystemRoot/workspace/'+stage[folder]+':'+command[i].split('=',1)[1]
 i=next(i for i,a in enumerate(command) if a.startswith('DYLD_FRAMEWORK_PATH='));command[i]='DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/workspace/runtime/mobileasset-download-attributes/frameworks:'+command[i].split('=',1)[1]
 return {**p,'command':command,'native_cryptex':stage,'source_mobileasset_download_attributes':attributes}
def environment(p):return m['environment'](p)
