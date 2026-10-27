#!/usr/bin/env python3
"""Verify actual Darwin waitid/nocancel child events, reaping and signal conversion."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='waitid-child-events-',dir=r/'runtime'))
stage=json.loads((r/a.stage).read_text());kernel=r/stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=r/'fixtures/hello/waitid-child-events.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration='config/direct-resource-tool-environment-v150.json')
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.quote(guest(binary))+'\nstatus=$?\nprintf "WAITID_STATUS %s\\n" "$status"\nexit "$status"\n')
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='45'
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:result=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^WAITID_STATUS (\d+)$',text,re.M);checks=re.findall(r'^WAITID_CHECKS (\d+)$',text,re.M)
passed=result.returncode==0 and statuses==['0'] and bool(checks) and 'WAITID_CHILD_EVENTS_VERIFIED' in text
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record=dict(verified=passed,stage=a.stage,kernel=str(kernel.relative_to(r)),kernel_sha256=sha(kernel),source=str(source.relative_to(r)),source_sha256=sha(source),binary_sha256=sha(binary),native_status=statuses,checks=int(checks[0]) if checks else None,outer_status=result.returncode,command=command,log=str(log.relative_to(r)),log_sha256=sha(log),scope=['syscall173 and416','no child ECHILD','invalid options','WNOHANG preserves siginfo without event','P_PID P_ALL P_PGID','stop/continue signal conversion','WNOWAIT repeat and actual reap','exit code and terminated signal'])
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2200:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if passed else 1)
