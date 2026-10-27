#!/usr/bin/env python3
"""Observe the exact native initialization API used by the paired securityd."""
from pathlib import Path
import hashlib,json,runpy,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;w=Path(tempfile.mkdtemp(prefix='securityd-sandbox-startup-',dir=r/'runtime'));src=r/'fixtures/hello/securityd-sandbox-initialization.c'
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(src),'-o',str(w/'probe.o')],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(w/'probe.o'),'-o',str(w/'probe')]]
for cmd in commands:subprocess.run(cmd,check=True)
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));p=m['profile'](stage='artifacts/private-procfs-auditsession84-stage.json',configuration='config/direct-resource-tool-environment-v150.json');cmd=p['command'][:-2]+['/Volumes/SystemRoot/workspace/'+str((w/'probe').relative_to(r))];cmd[3]='60'
with (w/'run.log').open('w') as out:res=subprocess.run(cmd,cwd=r,env=m['environment'](p),stdout=out,stderr=subprocess.STDOUT)
text=(w/'run.log').read_text();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();ok=res.returncode==0 and 'Sandbox profiles are not implemented' in text
record=dict(observed_unimplemented_startup_dependency=ok,outer_status=res.returncode,source=str(src.relative_to(r)),source_sha256=sha(src),driver_sha256=sha(Path(__file__)),commands=commands,stage='artifacts/private-procfs-auditsession84-stage.json',log=str((w/'run.log').relative_to(r)),log_sha256=sha(w/'run.log'),securityd_or_CMS_signing_ready=False)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-1500:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
