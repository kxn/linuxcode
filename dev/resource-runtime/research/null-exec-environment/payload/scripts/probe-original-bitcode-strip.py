#!/usr/bin/env python3
"""Run one original Framework bitcode-strip operation with private output."""
from pathlib import Path
import argparse,hashlib,json,runpy,shlex,subprocess,tempfile,time
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
for key in ['stage','configuration','input']:p.add_argument('--'+key,required=True)
p.add_argument('--capture',action='store_true');p.add_argument('--empty-environment',action='store_true');a=p.parse_args()
f=Path(tempfile.mkdtemp(prefix='original-bitcode-strip-',dir=r/'runtime'));guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r));sha=lambda n:hashlib.sha256(n.read_bytes()).hexdigest()
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';src=r/'fixtures/hello/spawn-diagnostic-command.c';obj=f/'spawn.o';exe=f/'spawn-diagnostic-command';target='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/bitcode_strip';output=f/'stripped'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O0','-g','-c',str(src),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','26.5','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
argv=[target,guest(r/a.input),'-r','-o',guest(output)];script=f/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join(([guest(exe)]+(['--empty-env'] if a.empty_environment else [])+argv) if a.capture or a.empty_environment else argv)+'\ns=$?\nprintf "ORIGINAL_BITCODE_STRIP_STATUS %s\\n" "$s"\nexit "$s"\n')
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile);cmd=list(profile['command'][:-2])+['/bin/bash',guest(script)];cmd[3]='80';capture=None
print('RUNNING',f.relative_to(r),flush=True)
with (f/'run.log').open('w') as out:
 proc=subprocess.Popen(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
 if a.capture:
  deadline=time.monotonic()+60;pid=None
  while proc.poll() is None and time.monotonic()<deadline:
   for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:args=path.read_bytes().split(b'\0')
    except OSError:continue
    if args[0]==guest(exe).encode():pid=int(path.parent.name);break
   if pid:break
   time.sleep(.005)
  if pid:
   kernel=r/profile['source_runtime']['LINUXCODE_LIBSYSTEM_KERNEL']['path'];nm=subprocess.check_output(['llvm-nm-19',str(kernel)],text=True);entry=int(next(l.split()[0] for l in nm.splitlines() if l.endswith(' _sys_posix_spawn')),16)
   region=None;map_deadline=time.monotonic()+2
   while region is None and time.monotonic()<map_deadline:
    region=next((l.split() for l in Path('/proc',str(pid),'maps').read_text().splitlines() if 'r-x' in l and l.endswith('/libsystem_kernel.dylib')),None)
    if region is None:time.sleep(.005)
   assert region is not None,'Diagnostic helper did not map the selected kernel'
   address=int(region[0].split('-')[0],16)-int(region[2],16)+entry;stem=f.name+'-fault'
   res=subprocess.run(['python3','scripts/capture-live-macho-fault.py','--pid',str(pid),'--stem',stem,'--timeout','50','--follow-spawn-suffix','/bitcode_strip','--spawn-entry',hex(address),'--spawn-entry-bytes',kernel.read_bytes()[entry:entry+16].hex()],cwd=r,stdout=out,stderr=subprocess.STDOUT);capture=dict(pid=pid,status=res.returncode,report='runtime/'+stem+'/result.json')
 status=proc.wait(timeout=100)
record=dict(verified=status==0 and output.is_file(),stage=a.stage,configuration=a.configuration,empty_environment=a.empty_environment,command=cmd,original_tool_arguments=argv,outer_status=status,capture=capture,input=dict(path=a.input,sha256=sha(r/a.input)),output=dict(size=output.stat().st_size,sha256=sha(output)) if output.exists() else None,log=str((f/'run.log').relative_to(r)),log_sha256=sha(f/'run.log'),files={str(n.relative_to(r)):sha(n) for n in [src,Path(__file__),script,r/a.stage,r/a.configuration]},full_goal_complete=False)
(f/'result.json').write_text(json.dumps(record,indent=2)+'\n');print('EVIDENCE',f/'result.json');raise SystemExit(0 if record['verified'] else 1)
