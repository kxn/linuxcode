#!/usr/bin/env python3
"""Retry the unchanged Apple codesign binary with the current native identity stack."""
from pathlib import Path
import hashlib,json,re,runpy,shlex,shutil,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='original-codesign-native-identity-',dir=r/'runtime'))
app=w/'iOSCocoaPodsSmoke.app';shutil.copytree(r/'runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos/iOSCocoaPodsSmoke.app',app)
tool=r/'runtime/recovery/macOS Base System/usr/bin/codesign';guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r))
script=w/'probe.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(tool),'--force','--sign','-','--timestamp=none',guest(app)])+'\ns=$?\nprintf "ORIGINAL_CODESIGN_NATIVE_IDENTITY_SIGN_STATUS %s\\n" "$s"\nif [ "$s" -ne 0 ]; then exit "$s"; fi\n'+shlex.join([guest(tool),'--verify','--strict','--verbose=2',guest(app)])+'\ns=$?\nprintf "ORIGINAL_CODESIGN_NATIVE_IDENTITY_VERIFY_STATUS %s\\n" "$s"\nexit "$s"\n')
m=runpy.run_path(str(r/'scripts/derq-runtime-profile.py'));p=m['profile'](derq_stage='artifacts/derq-original-v1-stage.json',identity_stage='artifacts/local-identity-store-readonly-v2-stage.json',identity_store='runtime/local-identity-xcode-empty-v1/store.plist',codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json',trace=True)
command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='90';env=m['environment'](p)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();sign=re.findall(r'^ORIGINAL_CODESIGN_NATIVE_IDENTITY_SIGN_STATUS (\d+)$',text,re.M);verify=re.findall(r'^ORIGINAL_CODESIGN_NATIVE_IDENTITY_VERIFY_STATUS (\d+)$',text,re.M);independent=None
if sign==['0'] and verify==['0']:
    independent=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify'](app)
ok=res.returncode==0 and sign==['0'] and verify==['0'] and bool(independent)
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();report=dict(verified=ok,outer_status=res.returncode,native_sign_status=sign,native_verify_status=verify,independent_signature_verification=independent,original_binary=str(tool.relative_to(r)),original_binary_sha256=sha(tool),log=str(log.relative_to(r)),log_sha256=sha(log),script_sha256=sha(script),test_driver_sha256=sha(__file__),zsign_invoked=False,original_binary_invoked_by_absolute_path=True,graphical_environment_removed=True,certificate_or_device_trust_verified=False)
(w/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(text[-3500:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
