#!/usr/bin/env python3
"""Check the actual successful Xcode product with native and independent verifiers."""
from pathlib import Path
import argparse,hashlib,json,os,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;a=argparse.ArgumentParser();a.add_argument('--build-report',required=True);a.add_argument('--native-stage',required=True);a.add_argument('--products',required=True);a.add_argument('--identity-store',default='runtime/local-identity-xcode-empty-v1/store.plist');a.add_argument('--report',required=True);args=a.parse_args();dest=r/args.report;assert not dest.exists()
build=json.loads((r/args.build_report).read_text());assert build['exit_status']==0 and build['native_xcode_status']==['0'] and build['native_codesign_stage']==args.native_stage and build['prebuild_command_verified']
text=(r/build['log']).read_text();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();assert sha(r/build['log'])==build['log_sha256'];assert re.search(r'^\*\* BUILD SUCCEEDED \*\*$',text,re.M)
products=r/args.products;app=products/'iOSCocoaPodsSmoke.app';archives=[products/'LocalMath/libLocalMath.a',products/'libPods-iOSCocoaPodsSmoke.a'];verify=runpy.run_path(str(r/'scripts/verify-adhoc-bundle.py'))['verify'];generic=runpy.run_path(str(r/'scripts/verify-adhoc-generic-file.py'))['verify'];independent_app=verify(app);independent_archives={str(p.relative_to(r)):generic(p) for p in archives}
for path in archives:assert path.read_bytes().startswith(b'!<arch>\n')
der_decode=runpy.run_path(str(r/'scripts/verify-entitlements-der.py'))['decode'];import plistlib
dd=products.parents[2];der_files={}
for path in dd.rglob('*.xcent.der'):
    xml=Path(str(path)[:-4]);assert der_decode(path.read_bytes())==plistlib.loads(xml.read_bytes());der_files[str(path.relative_to(r))]=sha(path)
m=runpy.run_path(str(r/'scripts/native-codesign-runtime-profile.py'));p=m['profile'](native_codesign_stage=args.native_stage,identity_store=args.identity_store);w=Path(tempfile.mkdtemp(prefix='native-signed-product-verify-',dir=r/'runtime'));guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r));lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','failed=0']
for i,target in enumerate([app,*archives]):lines += [shlex.join(['/usr/bin/codesign','--verify','--strict','--verbose=2',guest(target)]),'s=$?',f'printf "NATIVE_SIGNED_PRODUCT_{i}_STATUS %s\\n" "$s"','if [ "$s" -ne 0 ]; then failed=1; fi']
lines+=['exit "$failed"'];script=w/'verify.sh';script.write_text('\n'.join(lines)+'\n');command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='100';env=m['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
native=re.findall(r'^NATIVE_SIGNED_PRODUCT_([0-9]+)_STATUS ([0-9]+)$',log.read_text(),re.M);ok=res.returncode==0 and native==[('0','0'),('1','0'),('2','0')]
files=[app/'iOSCocoaPodsSmoke',app/'Info.plist',app/'_CodeSignature/CodeResources',*archives]
record=dict(verified=ok,original_xcodebuild_build_and_CodeSign_completed=True,build_report=args.build_report,build_report_sha256=sha(r/args.build_report),native_codesign_stage=args.native_stage,stage_sha256=sha(r/args.native_stage),native_product_statuses=native,outer_status=res.returncode,log=str(log.relative_to(r)),log_sha256=sha(log),application=str(app.relative_to(r)),independent_app_signature=independent_app,independent_archive_signatures=independent_archives,actual_xcode_DER_packaging=der_files,files={str(p.relative_to(r)):sha(p) for p in files},archive_signature_attributes={str(p.relative_to(r)):{name:hashlib.sha256(os.getxattr(p,name)).hexdigest() for name in os.listxattr(p) if name.startswith('user.com.apple.cs.')} for p in archives},zsign_used=False,ad_hoc_only=True,certificate_or_device_trust_verified=False,engine_generated_project=False,full_goal_complete=False)
dest.write_text(json.dumps(record,indent=2)+'\n');print(log.read_text()[-3000:]);print('EVIDENCE',dest);raise SystemExit(0 if ok else 1)
