#!/usr/bin/env python3
"""Launch Epic's locally acquired original Intel macOS dotnet under Darling."""
from pathlib import Path
import argparse,hashlib,json,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='unreal-dotnet-native-',dir=r/'runtime'))
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',default='artifacts/private-procfs-auditsession85-stage.json');parser.add_argument('--configuration',default='config/direct-resource-tool-environment-v150.json');parser.add_argument('--arguments-file');parser.add_argument('--temporary-stage');parser.add_argument('--resolver-stage');parser.add_argument('--libresolv-build');parser.add_argument('--nuget-http-cache');parser.add_argument('--cli-home');parser.add_argument('--coretls-build');parser.add_argument('--cfhelpers-build');parser.add_argument('--trace-memory',action='store_true');parser.add_argument('--security-services-candidate');parser.add_argument('--trace-files',action='store_true');parser.add_argument('--cwd',default='.');parser.add_argument('--timeout-seconds',type=int,default=90)
parser.add_argument('--scope',choices=['resource','caller'],default='resource',help='Keep the selected normal caller mapping only when explicitly requested')
parser.add_argument('--profile-report',help='Reuse the exact caller command prefix from a completed Xcode report; selected stage still supplies validated runtime binaries')
parser.add_argument('--environment-file',help='JSON string map of explicit guest environment additions, applied after the usual dotnet settings')
parser.add_argument('--executable',help='Original workspace-relative dotnet executable; defaults to the existing standalone copy')
parser.add_argument('--prepare-only',action='store_true',help='Build the command and report without starting native processes')
args=parser.parse_args();assert 1<=args.timeout_seconds<=86400
stage=args.stage;configuration=args.configuration
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));p=m['profile'](stage=stage,configuration=configuration)
if args.profile_report:
 assert args.scope=='caller', 'An actual caller command must not be replaced with the resource scope'
 snapshot=json.loads((r/args.profile_report).read_text());prefix=list(snapshot['command'])
 cut=prefix.index('/bin/bash');prefix=prefix[:cut]
 assert prefix[:3]==['timeout','-k','5'] and prefix.count('/usr/bin/env')==1
 # Preserve the real caller's scopes while applying explicitly selected
 # complete source libraries from this candidate configuration.
 for selected in p['direct_resource_environment'].get('source_library_directories', []):
  if selected['scope']=='all':
   index=next(i for i,v in enumerate(prefix) if v.startswith('DYLD_LIBRARY_PATH='))
   prefix[index]='DYLD_LIBRARY_PATH='+selected['directory']+':'+prefix[index].split('=',1)[1]
 p={**p,'command':prefix+['/bin/bash','unused']}
if args.temporary_stage:p=runpy.run_path(str(r/'scripts/native-temporary-runtime-profile.py'))['select'](p,args.temporary_stage)
guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
exe=(r/args.executable).resolve(strict=True) if args.executable else r/'runtime/unreal-dotnet-mac-x64-v1/Engine/Binaries/ThirdParty/DotNet/10.0/mac-x64/dotnet'
assert exe.is_relative_to(r) and exe.is_file()
arguments=json.loads((r/args.arguments_file).read_text()) if args.arguments_file else ['--info'];assert isinstance(arguments,list) and all(isinstance(v,str) for v in arguments)
working=(r/args.cwd).resolve();assert working.is_relative_to(r);cli_home=(r/args.cli_home).resolve(strict=True) if args.cli_home else folder/'cli-home';assert cli_home.is_relative_to(r/'runtime');cli_home.mkdir(exist_ok=True);cache=r/'runtime/unreal-nuget-packages-v1';cache.mkdir(exist_ok=True)
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+'cd '+shlex.quote(guest(working))+'\n'+shlex.join([guest(exe),*arguments])+'\ns=$?\nprintf "UNREAL_DOTNET_STATUS %s\\n" "$s"\nexit "$s"\n')
if args.resolver_stage:p=runpy.run_path(str(r/'scripts/native-resolver-runtime-profile.py'))['select'](p,args.resolver_stage)
if args.libresolv_build:p=runpy.run_path(str(r/'scripts/libresolv-source-runtime-profile.py'))['select'](p,args.libresolv_build)
normal_profile=p
cmd=list(p['command'][:-2]);scope=p['direct_resource_environment']['tool_environment']
if args.scope=='resource':
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
cmd+=['DOTNET_CLI_HOME='+guest(cli_home),'NUGET_PACKAGES='+guest(cache),'DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE=1','DOTNET_CLI_TELEMETRY_OPTOUT=1','DOTNET_GENERATE_ASPNET_CERTIFICATE=false','DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1','DOTNET_MULTILEVEL_LOOKUP=0']
extra=json.loads((r/args.environment_file).read_text()) if args.environment_file else {}
assert isinstance(extra,dict) and all(isinstance(k,str) and k and '=' not in k and '\0' not in k and isinstance(v,str) and '\0' not in v for k,v in extra.items())
assert not any(k.startswith(('DYLD_','DARLING_','LINUXCODE_')) and k!='LINUXCODE_POD_LIBRARY_DIR' for k in extra), 'Runtime selection belongs to the profile, not guest environment additions'
cmd += [k+'='+v for k,v in extra.items()]+['/bin/bash',guest(script)];cmd[3]=str(args.timeout_seconds);log=folder/'run.log';print('PREPARED' if args.prepare_only else 'RUNNING',folder.relative_to(r),flush=True)
if args.trace_memory:
 trace=r/'runtime/tools/strace-package/unpacked/usr/bin/strace';cmd=[str(trace),'-f','-Z','-s','160','-e','trace=mmap,mprotect,munmap,fcntl,ftruncate,memfd_create,process_vm_readv,process_vm_writev','-o',str(folder/'memory-failures.strace'),*cmd]
if args.trace_files:
 trace=r/'runtime/tools/strace-package/unpacked/usr/bin/strace';cmd=[str(trace),'-f','-s','180','-e','trace=stat,lstat,newfstatat,mkdir,mkdirat,rmdir,rename,renameat,renameat2,chmod,fchmodat','-o',str(folder/'files.strace'),*cmd]
result=None
if not args.prepare_only:
 with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=m['environment'](p),stdout=out,stderr=subprocess.STDOUT)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();text=log.read_text() if log.exists() else '';record=dict(original_macOS_x86_64_dotnet=True,prepared=True,runtime_execution_attempted=not args.prepare_only,verified=result is not None and result.returncode==0 and 'UNREAL_DOTNET_STATUS 0' in text,arguments=arguments,cwd=args.cwd,outer_status=None if result is None else result.returncode,command=cmd,stage=stage,temporary_stage=args.temporary_stage,resolver_stage=args.resolver_stage,libresolv_build=args.libresolv_build,configuration=configuration,coretls_build=args.coretls_build,cfhelpers_build=args.cfhelpers_build,trace_memory=args.trace_memory,nuget_http_cache=args.nuget_http_cache,cli_home=str(cli_home.relative_to(r)),security_services=p.get('native_security_services'),log=str(log.relative_to(r)),log_sha256=sha(log) if log.exists() else None,dotnet_sha256=sha(exe),UE_build_verified=False,source_sha256=sha(Path(__file__)),environment_scope=args.scope,profile_report=args.profile_report,guest_environment=extra,source_runtime=p['source_runtime'],input_files={name:sha(r/name) for name in [args.profile_report,args.environment_file,args.arguments_file] if name})
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if args.prepare_only or record['verified'] else 1)
