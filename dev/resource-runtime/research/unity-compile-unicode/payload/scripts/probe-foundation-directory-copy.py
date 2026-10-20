#!/usr/bin/env python3
"""Observe original Foundation directory-copy errors using the selected runtime."""
from pathlib import Path
import argparse,hashlib,json,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for key in ['configuration','stage','source']:p.add_argument('--'+key,required=True)
a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='foundation-directory-copy-',dir=root/'runtime'));sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';src='fixtures/hello/foundation-directory-copy.c';obj=folder/'test.o';program=folder/'test'
for c in [['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/src),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-lobjc','-no_fixup_chains','-no_adhoc_codesign',str(obj),'-o',str(program)]]:subprocess.run(c,cwd=root,check=True)
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for n in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(n,None)
command=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(command) if v.startswith(key+'='));command[i]=key+'='+scope[key]
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));source=(root/a.source).resolve();assert source.is_dir() and source.is_relative_to(root/'runtime');destination=folder/'copied';script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(program),guest(source),guest(destination)])+'\nstatus=$?\nprintf "DIRECTORY_COPY_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n');command+=['/bin/bash',guest(script)];command[3]='120';log=folder/'native.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();record=dict(diagnostic_only=True,outer_status=result.returncode,command=command,source=str(source.relative_to(root)),destination=str(destination.relative_to(root)),log=str(log.relative_to(root)),log_sha256=sha(log),configuration=a.configuration,stage=a.stage,sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/src]},full_goal_complete=False);(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(log.read_text()[-6000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(result.returncode)
