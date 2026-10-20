#!/usr/bin/env python3
"""Replay one captured original compiler command with isolated output paths."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--arguments',required=True);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();folder=Path(tempfile.mkdtemp(prefix='unity-clang-replay-',dir=root/'runtime'));guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
argv=json.loads((root/a.arguments).read_text());assert argv[0]=='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';outputs={}
for flag,name in [('-o','CMVideoSampling.o'),('-MF','CMVideoSampling.d'),('--serialize-diagnostics','CMVideoSampling.dia'),('-index-store-path','IndexStore')]:
 i=argv.index(flag);argv[i+1]=guest(folder/name);outputs[flag]=str((folder/name).relative_to(root))
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\ncd /Volumes/SystemRoot/workspace/runtime/unity-ios-cocoapods-ios26-v1/ios || exit 2\n'+shlex.join(argv)+'\nstatus=$?\nprintf "ORIGINAL_UNITY_CLANG_STATUS %s\\n" "$status"\nexit "$status"\n')
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(k,None)
cmd=profile['command'][:-2]+['/bin/bash',guest(script)];cmd[3]='240';log=folder/'run.log'
with log.open('w') as out:r=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ORIGINAL_UNITY_CLANG_STATUS ([0-9]+)$',t,re.M);obj=root/outputs['-o'];verified=r.returncode==0 and statuses==['0'] and obj.is_file() and obj.stat().st_size>0
record=dict(verified=verified,outer_status=r.returncode,native_statuses=statuses,arguments=argv,isolated_outputs=outputs,source_runtime=profile['source_runtime'],stage=a.stage,configuration=a.configuration,log=str(log.relative_to(root)),log_sha256=sha(log),files={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/a.arguments,root/a.configuration,root/a.stage,script]},full_goal_complete=False)
if obj.is_file():record['object_sha256']=sha(obj);record['object_bytes']=obj.stat().st_size
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(t[-4000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
