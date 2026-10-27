#!/usr/bin/env python3
"""Reproduce a spawn child inheriting a queue mutex held by another thread."""
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
p.add_argument('--configuration',default='config/direct-resource-tool-environment-v150.json');p.add_argument('--expect-blocked',action='store_true');a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='kqueue-spawn-fork-reset-',dir=r/'runtime'))
stage=json.loads((r/a.stage).read_text());kernel=r/stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']
symbols={}
for line in subprocess.check_output(['llvm-nm-19','--numeric-sort',str(kernel)],text=True).splitlines():
    match=re.match(r'^([0-9a-f]+)\s+\S\s+(_kq_mtx|_kqueue_impl)$',line)
    if match:symbols[match[2]]=int(match[1],16)
assert set(symbols)=={'_kq_mtx','_kqueue_impl'}
offset=symbols['_kq_mtx']-symbols['_kqueue_impl']
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=r/'fixtures/hello/kqueue-spawn-fork-reset.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration=a.configuration)
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(binary),str(offset)])+'\nstatus=$?\nprintf "KQUEUE_SPAWN_STATUS %s\\n" "$status"\nexit "$status"\n')
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='35'
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^KQUEUE_SPAWN_STATUS (\d+)$',text,re.M)
passed=res.returncode==0 and statuses==['0'] and 'KQUEUE_SPAWN_FORK_RESET_OK' in text
blocked=res.returncode!=0 and statuses==['142'] and 'KQUEUE_SPAWN_FORK_RESET_BEGIN ' in text and 'KQUEUE_SPAWN_FORK_RESET_OK' not in text
verified=blocked if a.expect_blocked else passed
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record=dict(verified=verified,expected_blocked=a.expect_blocked,spawn_completed=passed,baseline_block_reproduced=blocked,stage=a.stage,
            kernel=str(kernel.relative_to(r)),kernel_sha256=sha(kernel),private_mutex_symbol_offset=offset,
            source=str(source.relative_to(r)),source_sha256=sha(source),binary_sha256=sha(binary),
            native_status=statuses,outer_status=res.returncode,command=command,log=str(log.relative_to(r)),log_sha256=sha(log))
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2200:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
