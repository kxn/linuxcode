#!/usr/bin/env python3
"""Exercise the source NE query against genuine cross-process notify state."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage',required=True);p.add_argument('--configuration',required=True);a=p.parse_args()
c=json.loads((r/a.configuration).read_text());build=json.loads((r/c['resource_system_build']).read_text());helper=r/build['NE_session_helper']
folder=Path(tempfile.mkdtemp(prefix='ne-session-config-native-',dir=r/'runtime'));sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=r/'fixtures/hello/ne-session-config-state.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),str(helper),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration=a.configuration)
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.quote(guest(binary))+'\ns=$?\nprintf "NE_SESSION_CONFIG_STATUS %s\\n" "$s"\nexit "$s"\n')
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='60'
scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
    index=next(i for i,v in enumerate(command) if v.startswith(key+'='));command[index]=key+'='+scope[key]
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:result=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^NE_SESSION_CONFIG_STATUS (\d+)$',text,re.M);verified=result.returncode==0 and statuses==['0'] and 'NE_SESSION_REAL_NOTIFY_CONFIG_BITS_CACHED_POST_AND_EXEC_CHILD_VERIFIED' in text
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record=dict(verified=verified,stage=a.stage,configuration=a.configuration,source=str(source.relative_to(r)),source_sha256=sha(source),helper=str(helper.relative_to(r)),helper_sha256=sha(helper),binary_sha256=sha(binary),command=command,outer_status=result.returncode,native_status=statuses,log=str(log.relative_to(r)),log_sha256=sha(log),contract={'notification':'com.apple.neconfigurationchanged','state_bits':{'app_vpn':62,'always_on_vpn':61,'on_demand':63},'cached_until_post':True,'parent_and_exec_child_queries':True},notify_client_after_fork_without_exec_verified=False,UE_build_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-1700:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
