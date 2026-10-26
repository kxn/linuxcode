#!/usr/bin/env python3
"""Read real original-codesign metadata across distinct named XPC processes."""
from pathlib import Path
import argparse,hashlib,json,plistlib,runpy,shlex,shutil,struct,subprocess,tempfile,re
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--configuration',required=True);p.add_argument('--stage',required=True);a=p.parse_args();w=Path(tempfile.mkdtemp(prefix='peer-entitlements-',dir=r/'runtime'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(r));sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=r/'fixtures/hello/xpc-peer-entitlements.c';obj=w/'probe.o';exe=w/'unsigned'
commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-fblocks','-O1','-g','-c',str(source),'-o',str(obj)],['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-no_adhoc_codesign','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(exe)]]
for cmd in commands:subprocess.run(cmd,check=True)
for name in ['client','thin']:shutil.copy2(exe,w/name)
data=exe.read_bytes();cpu,subtype=struct.unpack_from('<II',data,4);header=struct.pack('>7I',0xcafebabe,1,cpu,subtype,4096,len(data),12);(w/'fat').write_bytes(header+bytes(4096-len(header))+data);(w/'fat').chmod(0o755)
values={'org.linuxcode.peer.true':True,'org.linuxcode.peer.false':False,'org.linuxcode.peer.string':'signed-peer-value','org.linuxcode.peer.number':947,'org.linuxcode.peer.array':['entry',True],'org.linuxcode.peer.nested':{'number':18}};client_values={'org.linuxcode.client':'separate-client-value'}
for name,value in [('server',values),('client',client_values)]:(w/(name+'.plist')).write_bytes(plistlib.dumps(value))
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile);scope=profile['direct_resource_environment']['tool_environment'];daemon_environment={v.split('=',1)[0]:v.split('=',1)[1] for v in profile['command'] if v.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH=','OBJC_DISABLE_TAGGED_POINTERS='))};daemon_environment.update(scope)
lines=['#!/bin/bash','set -e','ulimit -c 0','unset DISPLAY WAYLAND_DISPLAY XAUTHORITY']
for name in ['client','thin','fat']:
 lines += [shlex.join(['/usr/bin/codesign','--force','--sign','-','--timestamp=none','--entitlements',guest(w/('client.plist' if name=='client' else 'server.plist')),'--generate-entitlement-der',guest(w/name)]),shlex.join(['/usr/bin/codesign','--verify','--strict',guest(w/name)])]
labels=[]
for name in ['thin','fat','unsigned']:
 label='org.linuxcode.peer-signature.'+w.name+'.'+name;labels.append(label);job=dict(Label=label,ProgramArguments=[guest(w/name),'--server',label,'server'],MachServices={label:True},EnvironmentVariables=daemon_environment,StandardOutPath=guest(w/(name+'.log')),StandardErrorPath=guest(w/(name+'.log')));f=w/(name+'-job.plist');f.write_bytes(plistlib.dumps(job));f.chmod(0o644);lines += [shlex.join(['launchctl','load',guest(f)])]
lines += ["trap '"+'; '.join('launchctl remove '+label+' >/dev/null 2>&1' for label in labels)+"' EXIT"]
for name,label in zip(['thin','fat','unsigned'],labels):
 lines += [shlex.join([guest(w/'client'),'--client',label,'absent' if name=='unsigned' else 'signed']),f'printf "PEER_SIGNATURE_{name}_STATUS 0\\n"']
script=w/'run.sh';script.write_text('\n'.join(lines)+'\n');cmd=list(profile['command'][:-2])
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
 i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(key,None)
cmd+=['/bin/bash',guest(script)];cmd[3]='180';log=w/'run.log'
with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
t=log.read_text();statuses=re.findall(r'^PEER_SIGNATURE_(thin|fat|unsigned)_STATUS ([0-9]+)$',t,re.M);verified=result.returncode==0 and statuses==[('thin','0'),('fat','0'),('unsigned','0')] and t.count('XPC_SIGNED_PEER_METADATA_NATIVE_OK')==2 and 'XPC_UNSIGNED_PEER_METADATA_ABSENT_NATIVE_OK' in t
report=dict(verified=verified,stage=a.stage,configuration=a.configuration,outer_status=result.returncode,native_statuses=statuses,expected_server_entitlements=values,expected_client_entitlements=client_values,separate_processes=True,sync_and_async=True,stale_token_rejected=verified,metadata_reading_only=True,kernel_entitlement_enforcement_implemented=False,certificate_chain_trust_implemented=False,source_runtime=profile['source_runtime'],build_commands=commands,command=cmd,log=str(log.relative_to(r)),log_sha256=sha(log),files={str(q.relative_to(r)):sha(q) for q in [Path(__file__),source,script,w/'server.plist',w/'client.plist',r/a.stage,r/a.configuration]},full_goal_complete=False)
(w/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(t[-5500:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if verified else 1)
