#!/usr/bin/env python3
"""Register an owned framework service, activate it and query it from another process."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,runpy,shlex,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--framework-layout',choices=['flat','versioned'],default='flat');p.add_argument('--registration',choices=['explicit','discovery'],default='explicit');a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='xpc-user-bundle-',dir=root/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));source=root/'fixtures/hello/xpc-user-bundle.c';sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=folder/'probe.o';exe=folder/'probe'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-fblocks','-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-lobjc',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
framework=folder/'Fixture.framework';base=framework/'Versions/A' if a.framework_layout=='versioned' else framework;service=base/'XPCServices/Fixture.xpc';binary=service/'Contents/MacOS/FixtureService';binary.parent.mkdir(parents=True);shutil.copy2(exe,binary)
for path,info in [((base/'Resources/Info.plist' if a.framework_layout=='versioned' else framework/'Info.plist'),dict(CFBundleIdentifier='org.linuxcode.fixture.framework',CFBundlePackageType='FMWK',CFBundleExecutable='Fixture',CFBundleVersion='7.3')),(service/'Contents/Info.plist',dict(CFBundleIdentifier='org.linuxcode.user-bundle-fixture',CFBundlePackageType='XPC!',CFBundleExecutable='FixtureService',CFBundleVersion='7.3',XPCService=dict(ServiceType='User',RunLoopType='dispatch_main',EnvironmentVariables=dict(LINUXCODE_XPC_FIXTURE_VALUE='value-from-bundle-info'))))]:
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(plistlib.dumps(info))
if a.framework_layout=='versioned':
 (framework/'Versions/Current').symlink_to('A');(framework/'Resources').symlink_to('Versions/Current/Resources');(framework/'XPCServices').symlink_to('Versions/Current/XPCServices')
framework_source=root/'fixtures/hello/xpc-user-bundle-framework.c';framework_obj=folder/'framework.o';framework_image=base/'Fixture'
framework_commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-c',str(framework_source),'-o',str(framework_obj)],['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-install_name',guest(framework_image),str(framework_obj),'-o',str(framework_image)]]
for command in framework_commands:subprocess.run(command,check=True)
commands+=framework_commands
if a.framework_layout=='versioned':(framework/'Fixture').symlink_to('Versions/Current/Fixture')
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
script=folder/'run.sh';lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','failed=0']
for mode in ['auto' if a.registration=='discovery' else 'register','query']:
 lines.extend([shlex.join([guest(exe),mode,guest(framework),guest(service)]),'status=$?',f'printf "USER_BUNDLE_{mode.upper()}_STATUS %s\\n" "$status"','if [ "$status" -ne 0 ]; then failed=1; fi'])
lines.extend(['/bin/launchctl remove org.linuxcode.user-bundle-fixture || true','exit "$failed"']);script.write_text('\n'.join(lines)+'\n');cmd+=['/bin/bash',guest(script)];cmd[3]='100';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^USER_BUNDLE_(REGISTER|AUTO|QUERY)_STATUS ([0-9]+)$',t,re.M);verified=result.returncode==0 and statuses==[('AUTO' if a.registration=='discovery' else 'REGISTER','0'),('QUERY','0')] and 'USER_BUNDLE_REAL_ON_DEMAND_XPC_REPLY_OK' in t and 'USER_BUNDLE_CROSS_PROCESS_METADATA_OK' in t
report=dict(verified=verified,configuration=a.configuration,stage=a.stage,framework_layout=a.framework_layout,registration=a.registration,outer_status=result.returncode,native_statuses=statuses,source_runtime=profile['source_runtime'],build_commands=commands,command=cmd,log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,framework_source,script,root/a.stage,root/a.configuration]},Apple_CoreSimulator_service_verified=False,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-6000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
