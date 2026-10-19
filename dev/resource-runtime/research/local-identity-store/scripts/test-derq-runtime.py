#!/usr/bin/env python3
"""Run original derq and independently decode its actual DER output on Linux."""
from pathlib import Path
import hashlib,json,plistlib,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='original-derq-test-',dir=r/'runtime'))
fixtures=[{'application-identifier':'org.linuxcode.fixture','keychain-access-groups':['org.linuxcode.fixture']},{'groups':['a','b'],'nested':{'enabled':True,'disabled':False},'level':7,'name':'测试'}]
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r));lines=['#!/bin/bash','set -e','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for i,value in enumerate(fixtures):
    src=w/f'{i}.plist';src.write_bytes(plistlib.dumps(value));output=w/f'{i}.der'
    lines += [shlex.join(['/usr/bin/derq','query','-f','xml','-i',guest(src),'-o',guest(output),'--raw']),f'printf "DERQ_NATIVE_CASE_{i}_STATUS 0\\n"']
bad=w/'bad.plist';bad.write_bytes(b'<?xml version="1.0"?><plist><dict><key>broken</key>');lines+=['set +e',shlex.join(['/usr/bin/derq','query','-f','xml','-i',guest(bad),'-o',guest(w/'bad.der'),'--raw']),'s=$?','printf "DERQ_NATIVE_BAD_INPUT_STATUS %s\\n" "$s"','test "$s" -ne 0','exit $?']
script=w/'test.sh';script.write_text('\n'.join(lines)+'\n');stage='artifacts/derq-original-v1-stage.json';m=runpy.run_path(str(r/'scripts/derq-runtime-profile.py'));p=m['profile'](derq_stage=stage,identity_stage='artifacts/local-identity-store-readonly-v2-stage.json',identity_store='runtime/local-identity-xcode-empty-v1/store.plist',codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json')
command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='90';env=m['environment'](p)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,env=env,cwd=r,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();native=re.findall(r'^DERQ_NATIVE_CASE_(\d+)_STATUS 0$',text,re.M);badstatus=re.findall(r'^DERQ_NATIVE_BAD_INPUT_STATUS (\d+)$',text,re.M)
decode=runpy.run_path(str(r/'scripts/verify-entitlements-der.py'))['decode'];decoded=[]
for i,value in enumerate(fixtures):
    output=w/f'{i}.der'
    if output.is_file():
        try:decoded.append(decode(output.read_bytes())==value)
        except Exception:decoded.append(False)
ok=res.returncode==0 and native==['0','1'] and len(badstatus)==1 and int(badstatus[0])!=0 and decoded==[True,True]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();record=dict(verified=ok,outer_status=res.returncode,native_cases=native,bad_input_native_status=badstatus,independently_decoded=decoded,log=str(log.relative_to(r)),log_sha256=sha(log),stage=stage,stage_sha256=sha(r/stage),original_derq=True,test_driver_sha256=sha(__file__),full_xcode_signing_verified=False)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3500:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
