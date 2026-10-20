#!/usr/bin/env python3
"""Check that an awakened timed wait cannot time out a later indefinite wait."""
from pathlib import Path
import argparse,hashlib,json,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='wait-timer-isolation-',dir=root/'runtime'));sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=root/'fixtures/hello/wait-timer-isolation.c';obj=folder/'test.o';program=folder/'test'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
for c in commands:subprocess.run(c,check=True)
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for n in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(n,None)
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\n'+shlex.join([guest(program)])+'\nstatus=$?\nprintf "WAIT_TIMER_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n');command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='120';log=folder/'run.log'
with log.open('w') as out:r=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();verified=r.returncode==0 and 'WAIT_TIMER_DEADLINE_CANCELLATION_ISOLATION_OK' in t
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report=dict(verified=verified,stage=a.stage,configuration=a.configuration,outer_status=r.returncode,compile_commands=commands,command=command,log=str(log.relative_to(root)),log_sha256=sha(log),sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source]},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-3000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
