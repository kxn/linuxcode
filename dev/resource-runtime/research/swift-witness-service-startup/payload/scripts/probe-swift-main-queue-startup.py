#!/usr/bin/env python3
"""Check MainActor, main dispatch and yielding global tasks with the original compiler."""
from pathlib import Path
import argparse,hashlib,json,runpy,shlex,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for key in ['configuration','stage']:p.add_argument('--'+key,required=True)
a=p.parse_args();folder=Path(tempfile.mkdtemp(prefix='swift-main-queue-startup-',dir=root/'runtime'));fixture=root/'fixtures/hello/swift-main-queue-startup.swift';source=folder/'main.swift';shutil.copy2(fixture,source);program=folder/'test';guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root));compiler='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();installed=root/('runtime/state/prefix'+compiler);extracted=root/('runtime/xcode-extract/Xcode.app/Contents/Developer'+compiler.split('/Contents/Developer',1)[1]);assert sha(installed)==sha(extracted)
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for n in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(n,None)
compile=[compiler,guest(source),'-Onone','-target','x86_64-apple-macosx15.0','-sdk','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk','-module-cache-path',guest(folder/'module-cache'),'-o',guest(program)];script=folder/'compile.sh';script.write_text('#!/bin/bash\nulimit -c 0\n'+shlex.join(compile)+'\nstatus=$?\nprintf "SWIFT_FILE_INFO_COMPILE_STATUS %s\\n" "$status"\nexit "$status"\n');command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='180';log=folder/'compile.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
report=dict(diagnostic_only=True,configuration=a.configuration,stage=a.stage,compile_outer_status=result.returncode,compile_command=command,compile_log=str(log.relative_to(root)),compile_log_sha256=sha(log),original_compiler_sha256=sha(installed),sources={str(p.relative_to(root)):sha(p) for p in [Path(__file__),fixture]},full_goal_complete=False)
print('COMPILE',result.returncode,log.read_text()[-1800:],flush=True)
if result.returncode==0:
 command=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
 for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
  i=next(i for i,v in enumerate(command) if v.startswith(key+'='));command[i]=key+'='+scope[key]
 script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\n'+shlex.join([guest(program)])+'\nstatus=$?\nprintf "SWIFT_FILE_INFO_NATIVE_STATUS %s\\n" "$status"\nexit "$status"\n');command+=['/bin/bash',guest(script)];command[3]='120';log=folder/'native.log'
 with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
 report.update(outer_status=result.returncode,command=command,log=str(log.relative_to(root)),log_sha256=sha(log),program_sha256=sha(program));print(log.read_text()[-5000:],flush=True)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json');raise SystemExit(result.returncode)
