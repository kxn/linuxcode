#!/usr/bin/env python3
"""Force a real loader stack collision without replacing any live mapping."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for key in ['stage','configuration']:p.add_argument('--'+key,required=True)
p.add_argument('--force-collision',action='store_true');p.add_argument('--expect-startup-failure',action='store_true');a=p.parse_args();f=Path(tempfile.mkdtemp(prefix='mldr-stack-native-',dir=r/'runtime'));sha=lambda n:hashlib.sha256(n.read_bytes()).hexdigest();guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';src=r/'fixtures/hello/mldr-stack-collision-native.c';inject=r/'fixtures/hello/mldr-stack-collision-preload.c';obj=f/'probe.o';exe=f/'probe';preload=f/'force-collision.so'
commands=[['clang-19','-shared','-fPIC','-O2','-Wall','-Wextra',str(inject),'-o',str(preload)],['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(src),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','26.5','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
script=f/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(exe)]+(['--forced'] if a.force_collision else []))+'\ns=$?\nprintf "MLDR_STACK_NATIVE_STATUS %s\\n" "$s"\nexit "$s"\n')
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile);cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
if a.force_collision:cmd+=['LD_PRELOAD=/workspace/'+str(preload.relative_to(r))]
cmd+=['/bin/bash',guest(script)];cmd[3]='90';log=f/'run.log'
with log.open('w') as out:res=subprocess.run(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^MLDR_STACK_NATIVE_STATUS (\d+)$',text,re.M);success=res.returncode==0 and statuses==['0'] and 'MLDR_NATIVE_MAIN_STACK_COLLISION_512K_CAPACITY_MARKERS_AND_PTHREAD_OK' in text
negative=a.expect_startup_failure and res.returncode!=0 and 'Failed to allocate stack of 65536 bytes: 17 (File exists)' in text
record=dict(verified=negative if a.expect_startup_failure else success,native_success=success,expected_startup_failure_observed=bool(negative),forced_collision=a.force_collision,outer_status=res.returncode,native_statuses=statuses,stage=a.stage,configuration=a.configuration,command=cmd,build_commands=commands,log=str(log.relative_to(r)),log_sha256=sha(log),source_files={str(n.relative_to(r)):sha(n) for n in [Path(__file__),src,inject,r/a.stage]},test_injection_only=True,production_LD_PRELOAD_required=False,full_goal_complete=False)
(f/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2200:]);print('EVIDENCE',f/'result.json');raise SystemExit(0 if record['verified'] else 1)
