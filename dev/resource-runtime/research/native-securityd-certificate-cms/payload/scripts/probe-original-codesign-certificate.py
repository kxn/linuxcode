#!/usr/bin/env python3
"""Exercise original codesign with a private, temporary self-signed test identity.

This is a cryptographic compatibility probe, not Apple provisioning or trust.
Preparation can run while another serialized native build is active.
"""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,re,runpy,shlex,shutil,subprocess,tempfile

r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage',default='artifacts/private-procfs-auditsession80-stage.json')
p.add_argument('--configuration',default='config/direct-resource-tool-environment-v150.json')
p.add_argument('--identity-stage')
p.add_argument('--resource-scope',action='store_true',help='Diagnostic only: force the resource-tool framework scope')
p.add_argument('--with-trustd',action='store_true',help='Load the paired headless trust daemons in this private session')
p.add_argument('--launchctl',help='Uninstalled source launchctl for the private trustd job')
p.add_argument('--preflight-binary',help='Native per-API certificate/CMS diagnostic before original codesign')
p.add_argument('--trustd-identity-stage',help='Separate coherent Security scope for the paired legacy trustd process')
p.add_argument('--with-securityd',action='store_true',help='Also load the paired source SecurityServer for legacy CSSM module lookup')
p.add_argument('--securityd-build',help='Uninstalled complete source securityd and its exact private backend')
p.add_argument('--signer-debug-stage',help='Compile-time diagnostic signer stop library; requires an attached debugger to resume')
p.add_argument('--prepare-only',action='store_true');p.add_argument('--prepared-run')
a=p.parse_args();guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
sha=lambda n:hashlib.sha256(n.read_bytes()).hexdigest()
if a.prepared_run:
 f=(r/a.prepared_run).resolve();assert f.is_relative_to(r/'runtime')
 setup=json.loads((f/'prepared.json').read_text());a.stage=setup['stage'];a.configuration=setup['configuration']
else:
 f=Path(tempfile.mkdtemp(prefix='original-codesign-certificate-',dir=r/'runtime'));f.chmod(0o700)
 def openssl(*args):
  subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(f/'key.pem'),'-out',str(f/'certificate.pem'),'-subj','/CN=Linuxcode Temporary Code Signing Fixture','-days','2','-addext','basicConstraints=critical,CA:FALSE','-addext','keyUsage=critical,digitalSignature','-addext','extendedKeyUsage=codeSigning')
 openssl('x509','-in',str(f/'certificate.pem'),'-outform','DER','-out',str(f/'certificate.der'))
 openssl('rsa','-in',str(f/'key.pem'),'-traditional','-outform','DER','-out',str(f/'key.der'))
 for name in ['key.pem','key.der','certificate.pem','certificate.der']:(f/name).chmod(0o600)
 store=f/'identity-store.plist';store.write_bytes(plistlib.dumps(dict(version=1,locked=False,items=[dict(label='fixture',certificate=(f/'certificate.der').read_bytes(),privateKey=(f/'key.der').read_bytes())])));store.chmod(0o600)
 original=r/'runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos/iOSCocoaPodsSmoke.app'
 app=f/'iOSCocoaPodsSmoke.app';shutil.copytree(original,app)
 identity=hashlib.sha1((f/'certificate.der').read_bytes()).hexdigest().upper()
 args=['/usr/bin/codesign','--force','--sign',identity,'--timestamp=none','--verbose=4',guest(app)]
 script=f/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\nprintf "CERTIFICATE_CODESIGN_BEGIN\\n"\n'+shlex.join(args)+'\ns=$?\nprintf "CERTIFICATE_CODESIGN_SIGN_STATUS %s\\n" "$s"\nif [ "$s" -ne 0 ]; then exit "$s"; fi\n'+shlex.join(['/usr/bin/codesign','--verify','--strict','--verbose=4',guest(app)])+'\ns=$?\nprintf "CERTIFICATE_CODESIGN_VERIFY_STATUS %s\\n" "$s"\nexit "$s"\n')
 setup=dict(stage=a.stage,configuration=a.configuration,identity_SHA1=identity,public_certificate_SHA256=sha(f/'certificate.der'),application=str(app.relative_to(r)),temporary_self_generated_identity_only=True,certificate_chain_or_device_trust_verified=False,private_material_not_for_publication=True)
 (f/'prepared.json').write_text(json.dumps(setup,indent=2)+'\n')
if a.prepare_only:
 print('PREPARED',f.relative_to(r));raise SystemExit(0)
assert not (f/'result.json').exists()
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration);env=m['environment'](profile);cmd=list(profile['command'][:-2]);scope=profile['direct_resource_environment']['tool_environment']
if a.resource_scope:
 for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
  i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+scope[key]
setup['framework_scope']='resource-diagnostic' if a.resource_scope else 'normal-codesign'
if a.identity_stage:
 identity_stage=json.loads((r/a.identity_stage).read_text())
 for name,digest in identity_stage['files'].items():assert sha(r/name)==digest,name
 for key,leaf in [('DYLD_FRAMEWORK_PATH','frameworks'),('DYLD_LIBRARY_PATH','libraries')]:
  i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+guest(r/identity_stage['root']/leaf)+':'+cmd[i].split('=',1)[1]
 cmd.append('LINUXCODE_IDENTITY_TRACE=1');setup['identity_stage']=a.identity_stage
if a.signer_debug_stage:
 debug_stage=json.loads((r/a.signer_debug_stage).read_text());library=r/debug_stage['library']
 assert sha(library)==debug_stage['files'][debug_stage['library']]
 i=next(i for i,v in enumerate(cmd) if v.startswith('DYLD_LIBRARY_PATH='));cmd[i]='DYLD_LIBRARY_PATH='+guest(library.parent)+':'+cmd[i].split('=',1)[1]
 cmd.append('LINUXCODE_CODESIGN_DEBUG_STOP=1');setup['signer_debug_stage']=a.signer_debug_stage
for i,v in enumerate(cmd):
 if v.startswith('LINUXCODE_IDENTITY_STORE='):cmd[i]='LINUXCODE_IDENTITY_STORE='+guest(f/'identity-store.plist')
if a.with_trustd:
 ctl=guest((r/a.launchctl).resolve()) if a.launchctl else 'launchctl'
 if a.launchctl:setup['source_launchctl']={'path':a.launchctl,'sha256':sha(r/a.launchctl)}
 daemon_env=dict(v.split('=',1) for v in cmd if v.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH=','LINUXCODE_IDENTITY_STORE=','LINUXCODE_IDENTITY_TRACE=')))
 if a.trustd_identity_stage:
  daemon_stage=json.loads((r/a.trustd_identity_stage).read_text())
  for name,digest in daemon_stage['files'].items():
   runpy.run_path(str(r/'scripts/resolve-evidence-history.py'))['resolve'](name,digest)
  normal=dict(v.split('=',1) for v in profile['command'] if v.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH=')))
  for key,leaf in [('DYLD_FRAMEWORK_PATH','frameworks'),('DYLD_LIBRARY_PATH','libraries')]:daemon_env[key]=guest(r/daemon_stage['root']/leaf)+':'+normal[key]
  setup['trustd_identity_stage']=a.trustd_identity_stage
 prelude=[]
 jobs=(['LaunchDaemons/com.apple.securityd.plist'] if a.with_securityd else [])+['LaunchDaemons/com.apple.trustd.plist','LaunchAgents/com.apple.trustd.agent.plist']
 for source in jobs:
  job=plistlib.loads((r/'runtime/rootfs/usr/libexec/darling/System/Library'/source).read_bytes())
  label=job['Label'];job_env=dict(daemon_env)
  if a.securityd_build and label=='com.apple.securityd':
   source_build=json.loads((r/a.securityd_build).read_text())
   assert source_build['full_securityd_source_build']
   for key in ['binary','backend']:assert sha(r/source_build[key])==source_build[key+'_sha256'],key
   job['ProgramArguments'][0]=guest(r/source_build['binary'])
   job_env['DYLD_LIBRARY_PATH']=guest((r/source_build['backend']).parent)+':'+job_env['DYLD_LIBRARY_PATH']
   setup['securityd_build']=a.securityd_build
  job['EnvironmentVariables']={**job.get('EnvironmentVariables',{}),**job_env}
  # The private shell session has no Aqua/LoginWindow session type.  This
  # explicit headless probe retains the actual trustd --agent executable.
  job.pop('LimitLoadToSessionType',None);job['RunAtLoad']=True
  # Dedicated system accounts are absent in the private test prefix.  Run
  # these diagnostic services as the session user, not a host account.
  job.pop('UserName',None)
  job['ProgramArguments']=['/usr/bin/env',*[k+'='+v for k,v in job_env.items()],*job['ProgramArguments']]
  job['StandardOutPath']=job['StandardErrorPath']=guest(f/(label+'.log'))
  jobfile=f/(label+'.plist');jobfile.write_bytes(plistlib.dumps(job));jobfile.chmod(0o644)
  prelude+=[shlex.quote(ctl)+' remove '+shlex.quote(label)+' || true',shlex.quote(ctl)+' load '+shlex.quote(guest(jobfile)),shlex.quote(ctl)+' start '+shlex.quote(label),shlex.quote(ctl)+' list '+shlex.quote(label)]
 script=f/'run.sh';body=script.read_text();body=body.replace('printf "CERTIFICATE_CODESIGN_BEGIN', '\n'.join(prelude)+'\nprintf "CERTIFICATE_CODESIGN_BEGIN',1);script.write_text(body)
 setup['paired_trustd_jobs_requested']=True
if a.preflight_binary:
 binary=(r/a.preflight_binary).resolve();setup['preflight_binary']={'path':a.preflight_binary,'sha256':sha(binary)}
 script=f/'run.sh';body=script.read_text();body=body.replace('printf "CERTIFICATE_CODESIGN_BEGIN',shlex.join([guest(binary),guest(f/'preflight.cms')])+'\nprintf "CERTIFICATE_CODESIGN_BEGIN',1);script.write_text(body)
cmd+=['/bin/bash',guest(f/'run.sh')];cmd[3]='120';print('RUNNING',f.relative_to(r),flush=True)
with (f/'run.log').open('w') as out:res=subprocess.run(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=(f/'run.log').read_text();signed=re.findall(r'^CERTIFICATE_CODESIGN_SIGN_STATUS (\d+)$',text,re.M);verified=re.findall(r'^CERTIFICATE_CODESIGN_VERIFY_STATUS (\d+)$',text,re.M)
record=dict(**setup,outer_status=res.returncode,native_sign_status=signed,native_verify_status=verified,original_codesign_frontend_completed=res.returncode==0 and signed==['0'] and verified==['0'],CMS_cryptography_independently_verified=False,command=cmd,log=str((f/'run.log').relative_to(r)),log_sha256=sha(f/'run.log'),source_sha256=sha(Path(__file__)),full_goal_complete=False)
(f/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-4500:]);print('EVIDENCE',f/'result.json')
