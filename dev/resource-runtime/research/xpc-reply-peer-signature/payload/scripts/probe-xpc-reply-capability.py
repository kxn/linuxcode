#!/usr/bin/env python3
"""Check real synchronous and asynchronous request reply rights."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,runpy,shlex,struct,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--expected-status',choices=['0','1'],required=True);a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='xpc-reply-capability-',dir=root/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));source=root/'fixtures/hello/xpc-reply-capability.m';sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=folder/'probe.o';exe=folder/'probe'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-fblocks','-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-lobjc','-framework','Foundation','-framework','CoreFoundation',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
argv=[guest(exe)]
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\nexport DARLING_XPC_TRACE_LAUNCH_JOBS=1\n'+shlex.join(argv)+'\nstatus=$?\nprintf "ACTIVATION_ROUTING_STATUS %s\\n" "$status"\nexit "$status"\n')
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['/bin/bash',guest(script)];cmd[3]='100';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ACTIVATION_ROUTING_STATUS ([0-9]+)$',t,re.M);verified=result.returncode==int(a.expected_status) and statuses==[a.expected_status] and ('XPC_REAL_SYNC_AND_ASYNC_REPLY_CAPABILITIES_NATIVE_OK' in t if a.expected_status=='0' else any(marker in t for marker in ['REPLY_CAPABILITY_MISSING','REPLY_REMOTE_CONNECTION_MISSING']))
report=dict(verified=verified,expected_status=a.expected_status,stage=a.stage,configuration=a.configuration,outer_status=result.returncode,native_statuses=statuses,source_runtime=profile['source_runtime'],command=cmd,build_commands=commands,log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,script,root/a.stage,root/a.configuration]},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n');print(t[-5000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
