#!/usr/bin/env python3
"""Measure real Security/audit outputs in the selected resource-tool environment."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--configuration',required=True);parser.add_argument('--stage',required=True);args=parser.parse_args()
folder=Path(tempfile.mkdtemp(prefix='audit-session-lifecycle-',dir=root/'runtime'));sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source='fixtures/hello/audit-session-lifecycle.c';obj=folder/'test.o';program=folder/'test';sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','Security','-lSystem','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]
with (folder/'compile.log').open('w') as out:
 for command in commands:subprocess.run(command,cwd=root,check=True,stdout=out,stderr=subprocess.STDOUT)
mod=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));p=mod['profile'](stage=args.stage,configuration=args.configuration);env=mod['environment'](p)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
command=list(p['command'][:-2]);scope=p['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(command) if v.startswith(key+'='));command[i]=key+'='+scope[key]
guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n);script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(program.relative_to(root))])+'\nstatus=$?\nprintf "AUDIT_SESSION_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n');command+=['/bin/bash',guest(script.relative_to(root))];command[3]='120';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();verified=result.returncode==0 and 'AUDIT_SESSION_FORK_EXEC_CREATE_MASK_ISOLATION_MACH_TOKEN_AND_ERRORS_OK' in text and text.count('AUDIT_SESSION_EXEC_CHILD_OK')==2
record=dict(verified=verified,configuration=args.configuration,stage=args.stage,outer_status=result.returncode,command=command,compile_commands=commands,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root)),sources={n:sha(n) for n in [source,'scripts/probe-audit-session-lifecycle.py',args.configuration]},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
