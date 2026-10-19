#!/usr/bin/env python3
"""Test real native identity objects and noninteractive failure cases in Darling."""
from pathlib import Path
import hashlib,json,os,plistlib,re,runpy,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='local-identity-test-',dir=r/'runtime'));w.chmod(0o700)
def openssl(*args):subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(w/'key.pem'),'-out',str(w/'cert.pem'),'-subj','/CN=Linuxcode Local Identity Fixture','-days','2')
openssl('x509','-in',str(w/'cert.pem'),'-outform','DER','-out',str(w/'cert.der'))
openssl('rsa','-in',str(w/'key.pem'),'-traditional','-outform','DER','-out',str(w/'key.der'))
openssl('genrsa','-traditional','-out',str(w/'other.pem'),'2048');openssl('rsa','-in',str(w/'other.pem'),'-traditional','-outform','DER','-out',str(w/'other.der'))
for path in w.iterdir():path.chmod(0o600)
item=dict(label='fixture',certificate=(w/'cert.der').read_bytes(),privateKey=(w/'key.der').read_bytes())
def store(name,items,locked=False,mode=0o600):
    path=w/name;path.write_bytes(plistlib.dumps(dict(version=1,locked=locked,items=items)));path.chmod(mode);return path
valid=store('valid.plist',[item]);empty=store('empty.plist',[]);locked=store('locked.plist',[item],True)
bad=w/'bad.plist';bad.write_bytes(b'not a plist');bad.chmod(0o600)
mismatch=store('mismatch.plist',[{**item,'privateKey':(w/'other.der').read_bytes()}]);insecure=store('insecure.plist',[item],mode=0o644)
invalid=store('invalid-cert.plist',[{**item,'certificate':b'bad certificate'}])
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=r/'fixtures/hello/local-identity-store.c';obj=w/'test.o';binary=w/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','Security','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
stage='artifacts/local-identity-store-readonly-v2-stage.json';m=runpy.run_path(str(r/'scripts/local-identity-store-profile.py'));p=m['profile'](identity_stage=stage,identity_store=str(valid.relative_to(r)),codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json',trace=True)
script=w/'test.sh';import shlex
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(x) for x in [binary,valid,empty,locked,bad,w/'missing.plist',mismatch,insecure,invalid]])+'\ns=$?\nprintf "LOCAL_IDENTITY_NATIVE_STATUS %s\\n" "$s"\nexit "$s"\n')
command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='90';env=m['environment'](p)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();native=re.findall(r'^LOCAL_IDENTITY_NATIVE_STATUS (\d+)$',text,re.M);count=re.findall(r'^LOCAL_IDENTITY_STORE_NATIVE_OBJECTS_SIGNATURE_QUERY_SHAPES_AND_FAILURES_OK (\d+)$',text,re.M)
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
ok=res.returncode==0 and native==['0'] and len(count)==1
report=dict(verified=ok,native_status=native,outer_status=res.returncode,checks=count,log=str(log.relative_to(r)),log_sha256=sha(log),source_sha256=sha(source),stage=stage,stage_sha256=sha(r/stage),test_driver_sha256=sha(__file__),self_generated_test_identity_only=True,trust_verified=False,full_xcode_signing_verified=False)
(w/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(text[-5000:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
