#!/usr/bin/env python3
"""Check real exec/spawn NULL, empty and explicit environment vectors."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True);p.add_argument('--configuration',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='null-exec-environment-',dir=r/'runtime'));sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();guest=lambda f:'/Volumes/SystemRoot/workspace/'+str(f.relative_to(r))
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=r/'fixtures/hello/null-exec-environment.c';obj=folder/'probe.o';exe=folder/'probe'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','26.5','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(exe)])+'\nstatus=$?\nprintf "ACTIVATION_ROUTING_STATUS %s\\n" "$status"\nexit "$status"\n')
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile);cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['/bin/bash',guest(script)];cmd[3]='90';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ACTIVATION_ROUTING_STATUS ([0-9]+)$',t,re.M)
verified=result.returncode==0 and statuses==['0'] and 'NULLENV_EXEC_SPAWN_BINPREF_NULL_EMPTY_EXPLICIT_AND_PARENT_ISOLATION_OK' in t
record=dict(verified=verified,stage=a.stage,configuration=a.configuration,outer_status=result.returncode,native_statuses=statuses,source_runtime=profile['source_runtime'],command=cmd,build_commands=commands,log=str(log.relative_to(r)),log_sha256=sha(log),files={str(f.relative_to(r)):sha(f) for f in [Path(__file__),source,script,r/a.stage,r/a.configuration]},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(t[-4000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
