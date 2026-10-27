#!/usr/bin/env python3
"""Exercise real Darwin process enumeration against live namespace processes."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='proc-listpids-native-',dir=r/'runtime'));sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=r/'fixtures/hello/proc-listpids-native.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration='config/direct-resource-tool-environment-v153.json')
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r));script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.quote(guest(binary))+'\ns=$?\nprintf "PROC_LISTPIDS_STATUS %s\\n" "$s"\nexit "$s"\n');command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='55'
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:result=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^PROC_LISTPIDS_STATUS (\d+)$',text,re.M);checks=re.findall(r'^PROC_LISTPIDS_CHECKS (\d+)$',text,re.M);verified=result.returncode==0 and statuses==['0'] and bool(checks) and 'PROC_LISTPIDS_REAL_NAMESPACE_FAMILY_GROUP_UID_AND_BUFFER_ABI_OK' in text
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();record=dict(verified=verified,stage=a.stage,command=command,outer_status=result.returncode,native_status=statuses,checks=int(checks[0]) if checks else None,log=str(log.relative_to(r)),log_sha256=sha(log),source_sha256=sha(source),binary_sha256=sha(binary),supported_filters=['ALL','PPID','PGRP','UID','RUID'],controlling_TTY_and_kdebug_filter_supported=False,UE_build_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-1800:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
