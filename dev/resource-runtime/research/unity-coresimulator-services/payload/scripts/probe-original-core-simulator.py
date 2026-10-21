#!/usr/bin/env python3
"""Register the original CoreSimulator bundle and request its original service context."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--enable-private-core',action='store_true');a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='original-core-simulator-',dir=root/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));source=root/'fixtures/hello/original-core-simulator-context.c';sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=folder/'probe.o';exe=folder/'probe'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-lobjc',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
framework=root/'runtime/xcode-system-resources/Library/Developer/PrivateFrameworks/CoreSimulator.framework';argv=[guest(exe),guest(framework),guest(framework/'Versions/A/CoreSimulator')]

script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c '+('unlimited' if a.enable_private_core else '0')+'\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(argv)+'\nstatus=$?\nprintf "ORIGINAL_CORESIMULATOR_STATUS %s\\n" "$status"\nexit "$status"\n')
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['/bin/bash',guest(script)];cmd[3]='180';log=folder/'run.log'
with log.open('w') as out:r=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ORIGINAL_CORESIMULATOR_STATUS ([0-9]+)$',t,re.M);verified=r.returncode==0 and statuses==['0'] and 'CORE_SIMULATOR_CONTEXT present=1' in t
report=dict(verified=verified,outer_status=r.returncode,native_statuses=statuses,configuration=a.configuration,stage=a.stage,arguments=argv,build_commands=commands,source_runtime=profile['source_runtime'],log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,script,root/a.configuration,root/a.stage]},original_CoreSimulator_context_verified=verified,simulator_boot_verified=False,Storyboard_compilation_verified=False,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-7000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
