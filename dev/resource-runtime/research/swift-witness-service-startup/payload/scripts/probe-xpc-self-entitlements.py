#!/usr/bin/env python3
"""Check self metadata against fixtures signed by original codesign, in one session."""
from pathlib import Path
import argparse,hashlib,json,plistlib,re,runpy,shlex,shutil,subprocess,tempfile,struct
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args();w=Path(tempfile.mkdtemp(prefix='self-entitlements-',dir=r/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r));sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=r/'fixtures/hello/xpc-self-entitlements.c';build=[]
for architecture in ['x86_64']:
 obj=w/(architecture+'.o');exe=w/architecture
 commands=[['clang-19','-target',architecture+'-apple-macos11','-isysroot',str(sdk),'-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch',architecture,'-platform_version','macos','11','11','-no_adhoc_codesign','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
 for command in commands:subprocess.run(command,check=True);build.append(command)
unsigned=w/'unsigned';thin=w/'signed-thin';fat=w/'signed-fat';fat64=w/'signed-fat64';shutil.copy2(w/'x86_64',unsigned);shutil.copy2(w/'x86_64',thin)
data=(w/'x86_64').read_bytes();cpu,subtype=struct.unpack_from('<II',data,4)
for path,magic,entry in [(fat,0xcafebabe,struct.pack('>5I',cpu,subtype,4096,len(data),12)),(fat64,0xcafebabf,struct.pack('>IIQQII',cpu,subtype,4096,len(data),12,0))]:
 header=struct.pack('>II',magic,1)+entry;path.write_bytes(header+bytes(4096-len(header))+data);path.chmod(0o755)

values={'org.linuxcode.true':True,'org.linuxcode.false':False,'org.linuxcode.string':'original-signature-value','org.linuxcode.number':42,'org.linuxcode.array':['first',True],'org.linuxcode.nested':{'number':7}};entitlements=w/'entitlements.plist';entitlements.write_bytes(plistlib.dumps(values))
lines=['#!/bin/bash','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY','failed=0']
for label,exe in [('thin',thin),('fat',fat),('fat64',fat64)]:
 for action,args in [('sign',['--force','--sign','-','--timestamp=none','--entitlements',guest(entitlements),'--generate-entitlement-der']),('verify',['--verify','--strict'])]:
  lines += [shlex.join(['/usr/bin/codesign',*args,guest(exe)]),'status=$?',f'printf "SELF_METADATA_{label}_{action}_STATUS %s\\n" "$status"','if [ "$status" -ne 0 ]; then exit "$status"; fi']
for label,exe,mode in [('unsigned',unsigned,'absent'),('thin',thin,'signed'),('fat',fat,'signed'),('fat64',fat64,'signed')]:
 lines += [shlex.join([guest(exe),mode]),'status=$?',f'printf "SELF_METADATA_{label}_STATUS %s\\n" "$status"','if [ "$status" -ne 0 ]; then failed=1; fi']
lines+=['exit "$failed"'];script=w/'run.sh';script.write_text('\n'.join(lines)+'\n');m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
cmd+=['/bin/bash',guest(script)];cmd[3]='180';log=w/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^SELF_METADATA_(\w+)_STATUS ([0-9]+)$',t,re.M);expected=[('thin_sign','0'),('thin_verify','0'),('fat_sign','0'),('fat_verify','0'),('fat64_sign','0'),('fat64_verify','0'),('unsigned','0'),('thin','0'),('fat','0'),('fat64','0')];verified=result.returncode==0 and statuses==expected and t.count('SELF_ENTITLEMENTS_SIGNED_NATIVE_OK')==3 and 'SELF_ENTITLEMENTS_ABSENT_NATIVE_OK' in t
report=dict(verified=verified,configuration=a.configuration,stage=a.stage,outer_status=result.returncode,native_statuses=statuses,expected_entitlements=values,metadata_reading_only=True,kernel_entitlement_enforcement_implemented=False,foreign_process_query_implemented=False,source_runtime=profile['source_runtime'],build_commands=build,command=cmd,log=str(log.relative_to(r)),log_sha256=sha(log),files={str(q.relative_to(r)):sha(q) for q in [Path(__file__),source,entitlements,script,r/a.configuration,r/a.stage]},full_goal_complete=False)
(w/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-6000:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if verified else 1)
