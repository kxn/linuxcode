#!/usr/bin/env python3
"""Exercise real signal/S2C state reads during ordinary RPC logs and fatal exits."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='signal-diagnostic-runtime-',dir=r/'runtime'))
stage=json.loads((r/a.stage).read_text());kernel=r/stage['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path']
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
inputs=['fixtures/hello/signal-diagnostic-rpc-stress.c','fixtures/hello/fatal-signal-isolation.c'];binaries=[]
for name in inputs:
    source=r/name;obj=folder/(source.stem+'.o');binary=folder/source.stem
    subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-c',str(source),'-o',str(obj)],check=True)
    subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(kernel),str(obj),'-o',str(binary)],check=True);binaries.append(binary)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration='config/direct-resource-tool-environment-v150.json')
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
script=folder/'run.sh';lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','failed=0']
for i,binary in enumerate(binaries):lines += [shlex.quote(guest(binary)),'status=$?',f'printf "SIGNAL_CASE_{i}_STATUS %s\\n" "$status"','if [ "$status" -ne 0 ]; then failed=1; fi']
lines+=['exit "$failed"'];script.write_text('\n'.join(lines)+'\n')
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='100'
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:result=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^SIGNAL_CASE_(\d+)_STATUS (\d+)$',text,re.M)
passed=result.returncode==0 and statuses==[('0','0'),('1','0')] and 'SIGNAL_DIAGNOSTIC_RPC_STRESS_OK state_reads=128' in text and 'NATIVE_EIGHT_REAL_FATAL_CHILD_EXITS_PARENT_AND_SIBLING_SURVIVE_WITHOUT_GROUP_SIGNALS_OK' in text
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record=dict(verified=passed,stage=a.stage,native_statuses=statuses,outer_status=result.returncode,command=command,log=str(log.relative_to(r)),log_sha256=sha(log),sources={n:sha(r/n) for n in inputs},binaries={str(b.relative_to(r)):sha(b) for b in binaries},ordinary_RPC_logs=256,concurrent_thread_state_reads=128,actual_fatal_child_exits=8,signal_trace_written_directly_to_stderr='sigexc:   efl:' in text,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-1800:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if passed else 1)
