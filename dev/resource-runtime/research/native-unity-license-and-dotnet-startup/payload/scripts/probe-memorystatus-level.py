#!/usr/bin/env python3
"""Exercise real sysctl memory-availability ABI required by original CoreCLR."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import tempfile

r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True)
p.add_argument('--configuration',default='config/direct-resource-tool-environment-v150.json');p.add_argument('--expect-missing',action='store_true');a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='memorystatus-level-',dir=r/'runtime'))
stage=json.loads((r/a.stage).read_text());kernel=r/stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=r/'fixtures/hello/memorystatus-level.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration=a.configuration)
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(binary)]+(['missing'] if a.expect_missing else []))+'\nstatus=$?\nprintf "MEMSTATUS_STATUS %s\\n" "$status"\nexit "$status"\n')
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='35'
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
def host_available_percent():
    values={line.split(':',1)[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
    return values['MemAvailable']*100//values['MemTotal']
before=host_available_percent()
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
after=host_available_percent()
text=log.read_text();statuses=re.findall(r'^MEMSTATUS_STATUS (\d+)$',text,re.M)
passed=res.returncode==0 and statuses==['0'] and 'MEMSTATUS_READONLY_AND_BUFFER_ABI_OK' in text
blocked=res.returncode==0 and statuses==['0'] and 'MEMSTATUS_MISSING_REPRODUCED' in text
levels=re.findall(r'^MEMSTATUS_LEVEL (\d+)$',text,re.M)
reference_agrees=bool(levels) and min(before,after)-1<=int(levels[0])<=max(before,after)+1
passed=passed and reference_agrees
verified=blocked if a.expect_missing else passed
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record=dict(verified=verified,expected_missing=a.expect_missing,available_memory_API_verified=passed,baseline_missing_reproduced=blocked,host_available_percent_before=before,host_available_percent_after=after,reference_agrees=reference_agrees,stage=a.stage,
            kernel=str(kernel.relative_to(r)),kernel_sha256=sha(kernel),
            source=str(source.relative_to(r)),source_sha256=sha(source),binary_sha256=sha(binary),
            native_status=statuses,outer_status=res.returncode,command=command,log=str(log.relative_to(r)),log_sha256=sha(log))
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2200:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
