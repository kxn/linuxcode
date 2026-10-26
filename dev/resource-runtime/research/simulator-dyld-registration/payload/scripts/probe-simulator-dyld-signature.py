#!/usr/bin/env python3
"""Check descriptor passing and command-83 output/error ABI in native Darling."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);p.add_argument('--bootstrap',action='store_true');a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='simulator-dyld-signature-native-',dir=root/'runtime'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
source=root/('fixtures/hello/simulator-dyld-signature-bootstrap.c' if a.bootstrap else 'fixtures/hello/simulator-dyld-signature-native.c');sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';obj=folder/'probe.o';exe=folder/'probe'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','26.5','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
reference=json.loads((root/'runtime/dyld-sim-signature-reference-v1/metadata.json').read_text());original=root/reference['source'];data=bytearray(original.read_bytes());assert sha(original)==reference['source_sha256'];data[reference['slice_offset']+4096]^=1;bad=folder/'modified-dyld-sim';bad.write_bytes(data)
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(exe),guest(original),guest(bad)])+'\nstatus=$?\nprintf "ACTIVATION_ROUTING_STATUS %s\\n" "$status"\nexit "$status"\n')
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['/bin/bash',guest(script)];cmd[3]='100';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ACTIVATION_ROUTING_STATUS ([0-9]+)$',t,re.M);verified=result.returncode==0 and statuses==['0'] and 'REAL_APPLE_SIMULATOR_DYLD_SIGNATURE_REGISTRATION_NATIVE_OK' in t
if a.bootstrap:verified=verified and t.count('BOOTSTRAP_STATIC_FCNTL_ACTIVE command=83')==7
report=dict(verified=verified,bootstrap_static_entry=a.bootstrap,stage=a.stage,configuration=a.configuration,outer_status=result.returncode,native_statuses=statuses,source_runtime=profile['source_runtime'],command=cmd,build_commands=commands,log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),source,root/'fixtures/hello/simulator-dyld-signature-native.c',script,root/a.stage,root/a.configuration]},full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-7000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
