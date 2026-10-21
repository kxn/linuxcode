#!/usr/bin/env python3
"""Check the platform/version ABI against an independent guest sysctl query."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,runpy,shlex,struct,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='availability-version-',dir=root/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));source=root/'fixtures/hello/availability-version.c';sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=folder/'probe.o';exe=folder/'probe'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
stage_data=json.loads((root/a.stage).read_text());version=plistlib.loads((root/stage_data['system_version_binding']).read_bytes())['ProductVersion'];parts=[int(x) for x in version.split('.')];parts += [0]*(3-len(parts));expected=(parts[0]<<16)|(parts[1]<<8)|parts[2]
argv=[guest(exe),str(expected)]
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(argv)+'\nstatus=$?\nprintf "AVAILABILITY_VERSION_STATUS %s\\n" "$status"\nexit "$status"\n')
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['/bin/bash',guest(script)];cmd[3]='100';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^AVAILABILITY_VERSION_STATUS ([0-9]+)$',t,re.M);verified=result.returncode==0 and statuses==['0'] and 'AVAILABILITY_VERSION_NATIVE_OK' in t
report=dict(plist_OS_version=version,plist_packed_version=expected,comparison_reference='independent kern.osproductversion sysctl query in native probe',version_source_observations=re.findall(r'^AVAILABILITY_VERSION_SOURCES (.*)$',t,re.M),verified=verified,stage=a.stage,configuration=a.configuration,outer_status=result.returncode,native_statuses=statuses,source_runtime=profile['source_runtime'],command=cmd,build_commands=commands,log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,script,root/a.stage,root/a.configuration]},version_comparison_only=True,API_implementation_capability_not_claimed=True,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n');print(t[-5000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
