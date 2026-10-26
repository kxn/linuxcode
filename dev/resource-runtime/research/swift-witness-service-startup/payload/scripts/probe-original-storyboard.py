#!/usr/bin/env python3
"""Compile a real Unity launch storyboard with original tools and optional controls."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,runpy,shlex,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True)
p.add_argument('--trace-launch-jobs',action='store_true')
p.add_argument('--trace-os-log',action='store_true')
p.add_argument('--trace-job-state',action='store_true')
p.add_argument('--diagnostic-disable-volume-manager',action='store_true')
p.add_argument('--with-disk-services',action='store_true')
p.add_argument('--timeout',type=int,default=240)
a=p.parse_args();assert 1<=a.timeout<=600
folder=Path(tempfile.mkdtemp(prefix='original-storyboard-',dir=root/'runtime'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
source=root/'runtime/unity-ios-cocoapods-ios26-v1/ios/LaunchScreen-iPad.storyboard'
output=folder/'compiled';output.mkdir()
tool='/Applications/Xcode.app/Contents/Developer/usr/bin/ibtool'
argv=[tool,'--errors','--warnings','--notices','--module','uEmuera','--output-partial-info-plist',guest(folder/'SBPartialInfo.plist'),'--auto-activate-custom-fonts','--target-device','iphone','--target-device','ipad','--minimum-deployment-target','13.0','--output-format','human-readable-text',guest(source),'--compilation-directory',guest(output)]
m=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
files={str(q.relative_to(root)):sha(q) for q in [Path(__file__),source,root/a.configuration,root/a.stage]}
def build_c(relative,name,frameworks=()):
 src=root/relative;obj=folder/(name+'.o');exe=folder/name
 commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-Wno-deprecated-declarations','-c',str(src),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',*[v for f in frameworks for v in ['-framework',f]],str(obj),'-o',str(exe)]]
 for command in commands:subprocess.run(command,check=True)
 files[relative]=sha(src)
 return exe,commands
prelude=[];disk_services=None
if a.with_disk_services:
 daemon_environment={v.split('=',1)[0]:v.split('=',1)[1] for v in profile['command'] if v.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH=','OBJC_DISABLE_TAGGED_POINTERS='))}
 rows=[]
 for name in ['configd','diskarbitrationd']:
  original=root/('runtime/recovery/macOS Base System/usr/libexec/'+name)
  original_plist=root/('runtime/recovery/macOS Base System/System/Library/LaunchDaemons/com.apple.'+name+'.plist')
  job=plistlib.loads(original_plist.read_bytes())
  job['Program']=guest(original)
  if 'ProgramArguments' in job:job['ProgramArguments']=[job['Program'],*job['ProgramArguments'][1:]]
  job['EnvironmentVariables']={**job.get('EnvironmentVariables',{}),**daemon_environment}
  daemon_log=folder/(name+'.log');job['StandardOutPath']=job['StandardErrorPath']=guest(daemon_log)
  selected=folder/(name+'.plist');selected.write_bytes(plistlib.dumps(job));selected.chmod(0o644);files[str(selected.relative_to(root))]=sha(selected)
  prelude.append(shlex.join(['launchctl','load',guest(selected)])+' || exit $?')
  rows.append(dict(original=str(original.relative_to(root)),original_sha256=sha(original),original_plist=str(original_plist.relative_to(root)),original_plist_sha256=sha(original_plist),job=str(selected.relative_to(root)),job_sha256=sha(selected),log=str(daemon_log.relative_to(root))))
 client,commands=build_c('fixtures/hello/diskarbitration-session-ready.c','da-client',['CoreFoundation','DiskArbitration'])
 client_log=folder/'da-client.log'
 prelude += [shlex.join([guest(client)])+' > '+shlex.quote(guest(client_log))+' 2>&1','status=$?','printf "DA_SESSION_READY_STATUS %s\\n" "$status"','if [ "$status" -ne 0 ]; then exit "$status"; fi']
 disk_services=dict(daemons=rows,client_log=str(client_log.relative_to(root)),client_build_commands=commands)
control=None
if a.diagnostic_disable_volume_manager:
 control_exe,commands=build_c('fixtures/hello/coresim-service-volume-control.c','control')
 service='/Volumes/SystemRoot/workspace/runtime/xcode-system-resources/Library/Developer/PrivateFrameworks/CoreSimulator.framework/Versions/A/XPCServices/com.apple.CoreSimulator.CoreSimulatorService.xpc/Contents/MacOS/com.apple.CoreSimulator.CoreSimulatorService'
 prelude.append(shlex.join([guest(control_exe),service])+' || exit $?')
 control=dict(diagnostic_only=True,volume_manager_enabled=False,service_arguments=[service,'-EnableVolumeManager','NO'],build_commands=commands)
script=folder/'run.sh'
lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
if a.trace_launch_jobs:lines.append('export DARLING_XPC_TRACE_LAUNCH_JOBS=1')
if a.trace_os_log:lines += ['export DARLING_OS_LOG_STDERR=1','launchctl setenv DARLING_OS_LOG_STDERR 1 || exit $?']
lines += prelude
job_state_log=folder/'job-state.log'
if a.trace_job_state:
 lines += ['(', 'for ((tick=0; tick<'+str(a.timeout//2+1)+'; tick++)); do',
  'printf "JOB_STATE_TICK %s\\n" "$tick"',
  'launchctl list com.apple.CoreSimulator.simdiskimaged',
  'launchctl list com.apple.CoreSimulator.SimulatorTrampoline',
  'sleep 2', 'done', ') > '+shlex.quote(guest(job_state_log))+' 2>&1 &', 'job_monitor=$!']
lines += [shlex.join(argv),'status=$?']
if a.trace_job_state:lines += ['kill "$job_monitor" 2>/dev/null || true','wait "$job_monitor" 2>/dev/null || true']
lines += ['printf "ORIGINAL_STORYBOARD_STATUS %s\\n" "$status"','exit "$status"']
script.write_text('\n'.join(lines)+'\n');files[str(script.relative_to(root))]=sha(script)
cmd=profile['command'][:-2]+['/bin/bash',guest(script)];cmd[3]=str(a.timeout);log=folder/'run.log'
with log.open('w') as out:r=subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^ORIGINAL_STORYBOARD_STATUS ([0-9]+)$',t,re.M)
products={str(q.relative_to(root)):sha(q) for q in output.rglob('*') if q.is_file()}
verified=r.returncode==0 and statuses==['0'] and bool(products)
if disk_services:
 for row in disk_services['daemons']:
  q=root/row['log'];row['log_sha256']=sha(q) if q.is_file() else None
 q=root/disk_services['client_log'];disk_services['client_log_sha256']=sha(q) if q.is_file() else None
 disk_services['native_session_verified']=q.is_file() and 'DA_SESSION_READY_NATIVE_OK' in q.read_text() and 'DA_SESSION_READY_STATUS 0' in t
job_state=dict(log=str(job_state_log.relative_to(root)),log_sha256=sha(job_state_log)) if job_state_log.is_file() else None
report=dict(service_volume_control=control,disk_services=disk_services,trace_launch_jobs=a.trace_launch_jobs,trace_os_log=a.trace_os_log,job_state=job_state,timeout=a.timeout,verified=verified,outer_status=r.returncode,native_statuses=statuses,configuration=a.configuration,stage=a.stage,arguments=argv,products=products,source_runtime=profile['source_runtime'],log=str(log.relative_to(root)),log_sha256=sha(log),files=files,independent_storyboard_semantics_verified=False,full_goal_complete=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(t[-7000:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
