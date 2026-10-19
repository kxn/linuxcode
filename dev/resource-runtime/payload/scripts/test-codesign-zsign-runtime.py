#!/usr/bin/env python3
"""Exercise real Darwin codesign argv, ELF signing, hash verification and rejection."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,plistlib,re,runpy,shlex,shutil,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--codesign-stage',required=True);parser.add_argument('--source-app',type=Path,default=Path('runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos/iOSCocoaPodsSmoke.app'));a=parser.parse_args()
m=runpy.run_path(str(r/'scripts/codesign-zsign-runtime-profile.py'));p=m['profile'](codesign_stage=a.codesign_stage)
w=Path(tempfile.mkdtemp(prefix='codesign-zsign-test-',dir=r/'runtime'));guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r));sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
source=r/a.source_app;info=plistlib.loads((source/'Info.plist').read_bytes());executable=info['CFBundleExecutable'];apps={}
for name in ['plain','entitled']:
 app=w/(name+'.app');shutil.copytree(source,app);(app/'Sample.bin').write_bytes(bytes(range(256))*4);apps[name]=app
entitlements=w/'entitlements.plist';expected={'get-task-allow':True,'application-identifier':'org.linuxcode.iOSCocoaPodsSmoke','com.apple.security.application-groups':['group.org.linuxcode.fixture']};entitlements.write_bytes(plistlib.dumps(expected))
env=m['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
runs=[]
def invoke(label,entries):
 script=w/(label+'.sh');lines=['#!/bin/bash','set -e','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
 for name,argv,success in entries:
  lines+=['set +e',shlex.join(argv),'status=$?',f'printf "CODESIGN_ADAPTER_CASE {name} %s\\n" "$status"','set -e','test "$status" '+('-eq 0' if success else '-ne 0')]
 script.write_text('\n'.join(lines)+'\n');command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='120';log=w/(label+'.log')
 with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
 text=log.read_text();statuses=re.findall('^CODESIGN_ADAPTER_CASE ([a-z0-9-]+) ([0-9]+)$',text,re.M)
 valid=res.returncode==0 and len(statuses)==len(entries) and all(got[0]==entry[0] and ((int(got[1])==0)==entry[2]) for got,entry in zip(statuses,entries))
 runs.append(dict(label=label,command=command,outer_status=res.returncode,verified=valid,native_statuses=statuses,log=str(log.relative_to(r)),log_sha256=sha(log),script=str(script.relative_to(r)),script_sha256=sha(script)))
 print(label,res.returncode,valid,text[-3500:],flush=True)
 return valid
ok=invoke('real-sign-and-verify',[
 ('plain-sign',['/usr/bin/codesign','--force','--sign','-','--timestamp=none','--generate-entitlement-der',guest(apps['plain'])],True),
 ('plain-verify',['/usr/bin/codesign','--verify','--strict','--verbose=2',guest(apps['plain'])],True),
 ('entitled-sign',['/usr/bin/codesign','--force','--sign','-','--timestamp=none','--entitlements',guest(entitlements),'--generate-entitlement-der',guest(apps['entitled'])],True),
 ('entitled-verify',['/usr/bin/codesign','--verify','--strict','--entitlements',guest(entitlements),'--generate-entitlement-der',guest(apps['entitled'])],True)])
independent={};rejections=[]
if ok:
 verify=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify']
 independent={name:verify(app) for name,app in apps.items()}
 for name in ['code-page','info-plist','sealed-resource','added-resource']:
  app=w/(name+'.app');shutil.copytree(apps['plain'],app)
  if name=='code-page':file=app/executable;raw=bytearray(file.read_bytes());raw[0x4000]^=1;file.write_bytes(raw)
  elif name=='info-plist':file=app/'Info.plist';data=plistlib.loads(file.read_bytes());data['CFBundleName']='tampered';file.write_bytes(plistlib.dumps(data))
  elif name=='sealed-resource':(app/'Sample.bin').write_bytes(b'tampered')
  else:(app/'Added.bin').write_bytes(b'unsealed')
  rejections.append((name,['/usr/bin/codesign','--verify','--strict',guest(app)],False))
 before={str(path.relative_to(apps['plain'])):sha(path) for path in apps['plain'].rglob('*') if path.is_file()}
 extra=[('unsupported-identity',['/usr/bin/codesign','--force','--sign','Unsupported Identity',guest(apps['plain'])],False),('unsupported-option',['/usr/bin/codesign','--force','--sign','-','--not-a-real-option',guest(apps['plain'])],False),('unsupported-deep',['/usr/bin/codesign','--verify','--deep',guest(apps['plain'])],False)]
 for name,value in [('unsupported-integer-entitlement',7),('unsupported-data-entitlement',b'not-a-text-string')]:
  file=w/(name+'.plist');file.write_bytes(plistlib.dumps({'unsupported-fixture-value':value}));extra.append((name,['/usr/bin/codesign','--force','--sign','-','--entitlements',guest(file),'--generate-entitlement-der',guest(apps['plain'])],False))
 ok=invoke('tamper-and-unsupported-rejections',rejections+extra)
 after={str(path.relative_to(apps['plain'])):sha(path) for path in apps['plain'].rglob('*') if path.is_file()};assert before==after
entry=r/p['source_codesign_adapter']['original_persistent_codesign'];assert sha(entry)==p['source_codesign_adapter']['original_persistent_codesign_sha256']
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=bool(ok and independent and len(rejections)==4),codesign_stage=a.codesign_stage,codesign_stage_sha256=sha(r/a.codesign_stage),runs=runs,independent_signature_checks=independent,entitlements=expected,negative_cases=[e[0] for e in rejections]+([e[0] for e in extra] if independent else []),source_runtime=p['source_runtime'],test_driver_sha256=sha(__file__),source_application=str(source.relative_to(r)),persistent_codesign_unchanged=True,original_codesign_frontend_used=False,xcodebuild_signing_step_integrated=False,certificate_or_device_trust_verified=False,nested_code_signing_implemented=False)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',w/'result.json',flush=True);raise SystemExit(0 if record['verified'] else 1)
