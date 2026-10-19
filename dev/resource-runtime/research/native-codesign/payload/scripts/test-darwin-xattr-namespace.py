#!/usr/bin/env python3
"""Verify real Darwin xattr behavior and independently inspect its Linux storage."""
from pathlib import Path
import argparse,hashlib,json,os,re,runpy,subprocess,tempfile
a=argparse.ArgumentParser();a.add_argument("--xattr-stage",default="artifacts/xattr-runtime-v1-stage.json");args=a.parse_args()
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='darwin-xattr-test-',dir=r/'runtime'));output=w/'output';output.mkdir();src=r/'fixtures/hello/darwin-xattr-namespace.c';sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=w/'test.o';binary=w/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(src),'-o',str(obj)],check=True);subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
m=runpy.run_path(str(r/'scripts/xattr-runtime-profile.py'));stage=args.xattr_stage;p=m['profile'](xattr_stage=stage,derq_stage='artifacts/derq-original-v1-stage.json',identity_stage='artifacts/local-identity-store-readonly-v2-stage.json',identity_store='runtime/local-identity-xcode-empty-v1/store.plist',codesign_stage='artifacts/codesign-zsign-adhoc-v2-stage.json');guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r))
script=w/'test.sh';import shlex
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(binary),guest(output)])+'\ns=$?\nprintf "DARWIN_XATTR_NATIVE_STATUS %s\\n" "$s"\nexit "$s"\n');command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='100';env=m['environment'](p)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();status=re.findall(r'^DARWIN_XATTR_NATIVE_STATUS (\d+)$',text,re.M);counts=re.findall(r'^DARWIN_XATTR_REAL_NAMESPACE_PATH_FD_SIZE_ERRORS_SYMLINK_AND_QUARANTINE_ALIAS_OK (\d+)$',text,re.M);storage=False
if res.returncode==0 and status==['0'] and counts:
    item=output/'item';assert os.getxattr(item,'user.com.apple.cs.Test')==bytes([0,128,255,65]);assert os.getxattr(item,'user.user.com.apple.quarantine')==b'shadow';assert os.getxattr(item,'user.com.apple.quarantine').startswith(b'0000;');assert 'user.linuxcode.alpha' not in os.listxattr(item) and 'user.user.linuxcode.alpha' not in os.listxattr(item);storage=True
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();ok=res.returncode==0 and status==['0'] and len(counts)==1 and storage
record=dict(verified=ok,outer_status=res.returncode,native_status=status,checks=counts,physical_Linux_storage_verified=storage,log=str(log.relative_to(r)),log_sha256=sha(log),source_sha256=sha(src),stage=stage,stage_sha256=sha(r/stage),test_driver_sha256=sha(__file__),native_codesign_verified=False)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3000:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
