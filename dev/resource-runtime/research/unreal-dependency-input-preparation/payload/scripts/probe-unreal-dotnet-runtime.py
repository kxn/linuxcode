#!/usr/bin/env python3
"""Launch Epic's locally acquired original Intel macOS dotnet under Darling."""
from pathlib import Path
import argparse,hashlib,json,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='unreal-dotnet-native-',dir=r/'runtime'))
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',default='artifacts/private-procfs-auditsession85-stage.json');parser.add_argument('--configuration',default='config/direct-resource-tool-environment-v150.json');parser.add_argument('--arguments-file');parser.add_argument('--temporary-stage');parser.add_argument('--resolver-stage');parser.add_argument('--libresolv-build');parser.add_argument('--nuget-http-cache');parser.add_argument('--coretls-build');parser.add_argument('--cfhelpers-build');parser.add_argument('--trace-memory',action='store_true');parser.add_argument('--security-services-candidate');parser.add_argument('--trace-files',action='store_true');parser.add_argument('--cwd',default='.');parser.add_argument('--timeout-seconds',type=int,default=90);args=parser.parse_args();assert 1<=args.timeout_seconds<=86400
stage=args.stage;configuration=args.configuration
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));p=m['profile'](stage=stage,configuration=configuration)
if args.temporary_stage:p=runpy.run_path(str(r/'scripts/native-temporary-runtime-profile.py'))['select'](p,args.temporary_stage)
guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
exe=r/'runtime/unreal-dotnet-mac-x64-v1/Engine/Binaries/ThirdParty/DotNet/10.0/mac-x64/dotnet'
arguments=json.loads((r/args.arguments_file).read_text()) if args.arguments_file else ['--info'];assert isinstance(arguments,list) and all(isinstance(v,str) for v in arguments)
working=(r/args.cwd).resolve();assert working.is_relative_to(r);(folder/'cli-home').mkdir();cache=r/'runtime/unreal-nuget-packages-v1';cache.mkdir(exist_ok=True)
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+'cd '+shlex.quote(guest(working))+'\n'+shlex.join([guest(exe),*arguments])+'\ns=$?\nprintf "UNREAL_DOTNET_STATUS %s\\n" "$s"\nexit "$s"\n')
if args.resolver_stage:p=runpy.run_path(str(r/'scripts/native-resolver-runtime-profile.py'))['select'](p,args.resolver_stage)
if args.libresolv_build:p=runpy.run_path(str(r/'scripts/libresolv-source-runtime-profile.py'))['select'](p,args.libresolv_build)
normal_profile=p
cmd=list(p['command'][:-2]);scope=p['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
if args.coretls_build:
 p=runpy.run_path(str(r/'scripts/coretls-source-runtime-profile.py'))['select']({**p,'command':cmd},args.coretls_build);cmd=list(p['command'])
if args.cfhelpers_build:
 p=runpy.run_path(str(r/'scripts/coretls-cfhelpers-runtime-profile.py'))['select']({**p,'command':cmd},args.cfhelpers_build);cmd=list(p['command'])
if args.security_services_candidate:
 services_profile=runpy.run_path(str(r/'scripts/native-security-services-profile.py'))['select'](normal_profile,args.security_services_candidate);p={**p,'native_security_services':services_profile['native_security_services']}
 services=p['native_security_services'];text=script.read_text();text=text.replace('cd '+shlex.quote(guest(working)),services['startup']+'trap '+shlex.quote(services['cleanup'])+' EXIT\n'+'cd '+shlex.quote(guest(working)),1);script.write_text(text)
if args.nuget_http_cache:
 http_cache=(r/args.nuget_http_cache).resolve(strict=True);assert http_cache.is_dir() and http_cache.is_relative_to(r/'runtime');cmd+=['NUGET_HTTP_CACHE_PATH='+guest(http_cache)]
cmd+=['DOTNET_CLI_HOME='+guest(folder/'cli-home'),'NUGET_PACKAGES='+guest(cache),'DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE=1','DOTNET_CLI_TELEMETRY_OPTOUT=1','DOTNET_GENERATE_ASPNET_CERTIFICATE=false','DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1','DOTNET_MULTILEVEL_LOOKUP=0','/bin/bash',guest(script)];cmd[3]=str(args.timeout_seconds);log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
if args.trace_memory:
 trace=r/'runtime/tools/strace-package/unpacked/usr/bin/strace';cmd=[str(trace),'-f','-Z','-s','160','-e','trace=mmap,mprotect,munmap,fcntl,ftruncate,memfd_create,process_vm_readv,process_vm_writev','-o',str(folder/'memory-failures.strace'),*cmd]
if args.trace_files:
 trace=r/'runtime/tools/strace-package/unpacked/usr/bin/strace';cmd=[str(trace),'-f','-s','180','-e','trace=stat,lstat,newfstatat,mkdir,mkdirat,rmdir,rename,renameat,renameat2,chmod,fchmodat','-o',str(folder/'files.strace'),*cmd]
with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=m['environment'](p),stdout=out,stderr=subprocess.STDOUT)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();text=log.read_text();record=dict(original_macOS_x86_64_dotnet=True,verified=result.returncode==0 and 'UNREAL_DOTNET_STATUS 0' in text,arguments=arguments,cwd=args.cwd,outer_status=result.returncode,command=cmd,stage=stage,temporary_stage=args.temporary_stage,resolver_stage=args.resolver_stage,libresolv_build=args.libresolv_build,configuration=configuration,coretls_build=args.coretls_build,cfhelpers_build=args.cfhelpers_build,trace_memory=args.trace_memory,nuget_http_cache=args.nuget_http_cache,security_services=p.get('native_security_services'),log=str(log.relative_to(r)),log_sha256=sha(log),dotnet_sha256=sha(exe),UE_build_verified=False,source_sha256=sha(Path(__file__)))
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if record['verified'] else 1)
