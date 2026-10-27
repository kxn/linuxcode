#!/usr/bin/env python3
"""Launch Epic's locally acquired original Intel macOS dotnet under Darling."""
from pathlib import Path
import hashlib,json,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='unreal-dotnet-native-',dir=r/'runtime'))
stage='artifacts/private-procfs-auditsession85-stage.json';configuration='config/direct-resource-tool-environment-v150.json'
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));p=m['profile'](stage=stage,configuration=configuration)
guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
exe=r/'runtime/unreal-dotnet-mac-x64-v1/Engine/Binaries/ThirdParty/DotNet/10.0/mac-x64/dotnet'
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(exe),'--info'])+'\ns=$?\nprintf "UNREAL_DOTNET_STATUS %s\\n" "$s"\nexit "$s"\n')
cmd=list(p['command'][:-2]);scope=p['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['DOTNET_CLI_TELEMETRY_OPTOUT=1','DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1','DOTNET_MULTILEVEL_LOOKUP=0','/bin/bash',guest(script)];cmd[3]='90';log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=m['environment'](p),stdout=out,stderr=subprocess.STDOUT)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();text=log.read_text();record=dict(original_macOS_x86_64_dotnet=True,verified=result.returncode==0 and 'UNREAL_DOTNET_STATUS 0' in text,outer_status=result.returncode,command=cmd,stage=stage,configuration=configuration,log=str(log.relative_to(r)),log_sha256=sha(log),dotnet_sha256=sha(exe),UE_build_verified=False,source_sha256=sha(Path(__file__)))
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if record['verified'] else 1)
