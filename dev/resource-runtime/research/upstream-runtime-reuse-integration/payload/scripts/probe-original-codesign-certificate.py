#!/usr/bin/env python3
"""Exercise original codesign with a private, temporary self-signed test identity.

This is a cryptographic compatibility probe, not Apple provisioning or trust.
Preparation can run while another serialized native build is active.
"""
from pathlib import Path
import argparse,hashlib,json,os,plistlib,re,runpy,shlex,shutil,subprocess,tempfile

r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--unified',action='store_true',help='Use one shared runtime from bootstrap; no certificate selector, daemon jobs or DYLD changes')
p.add_argument('--small-binary',default='runtime/objc-claim-return-3f8d4_7j/probe',help='Existing small Mach-O copied into an independent Mac app in unified mode')
p.add_argument('--common-security-build',default='runtime/local-identity-store-common-owner-v1/build.json')
p.add_argument('--stage',default='artifacts/private-procfs-auditsession80-stage.json')
p.add_argument('--configuration',default='config/direct-resource-tool-environment-v150.json')
p.add_argument('--identity-stage')
p.add_argument('--resource-scope',action='store_true',help='Diagnostic only: force the resource-tool framework scope')
p.add_argument('--with-trustd',action='store_true',help='Load the paired headless trust daemons in this private session')
p.add_argument('--launchctl',help='Uninstalled source launchctl for the private trustd job')
p.add_argument('--preflight-only',action='store_true',help='Unified mode: run the existing certificate/CMS preflight instead of codesign')
p.add_argument('--preflight-binary',help='Native per-API certificate/CMS diagnostic before original codesign')
p.add_argument('--trustd-identity-stage',help='Separate coherent Security scope for the paired legacy trustd process')
p.add_argument('--with-securityd',action='store_true',help='Also load the paired source SecurityServer for legacy CSSM module lookup')
p.add_argument('--securityd-build',help='Uninstalled complete source securityd and its exact private backend')
p.add_argument('--signer-debug-stage',help='Compile-time diagnostic signer stop library; requires an attached debugger to resume')
p.add_argument('--candidate',help='Pinned complete signing candidate for an existing research workspace')
p.add_argument('--imported-store',help='Caller-provided native identity store instead of generating a key')
p.add_argument('--certificate',help='Public PEM certificate matching the imported signing identity')
p.add_argument('--synthetic-test-identity',action='store_true',help='Explicitly label a caller-supplied generated test identity')
p.add_argument('--prepare-only',action='store_true');p.add_argument('--prepared-run')
a=p.parse_args();guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
sha=lambda n:hashlib.sha256(n.read_bytes()).hexdigest()
if a.unified:
 assert not any([a.candidate,a.resource_scope,a.identity_stage,a.with_trustd,a.launchctl,a.trustd_identity_stage,a.with_securityd,a.securityd_build,a.signer_debug_stage]), 'unified mode forbids legacy library/service selection'
if a.preflight_only:assert a.unified and a.preflight_binary, '--preflight-only needs --unified and --preflight-binary'
if a.candidate:
 candidate=json.loads((r/a.candidate).read_text())
 allowed={'stage','configuration','identity_stage','trustd_identity_stage','securityd_build','launchctl'}
 for key,row in candidate['inputs'].items():
  assert key in allowed and sha(r/row['path'])==row['sha256'],key
  setattr(a,key,row['path'])
 a.with_trustd=True;a.with_securityd=True
if a.prepared_run:
 f=(r/a.prepared_run).resolve();assert f.is_relative_to(r/'runtime')
 setup=json.loads((f/'prepared.json').read_text())
 assert bool(setup.get('unified_runtime'))==a.unified
 if not a.unified:a.stage=setup['stage'];a.configuration=setup['configuration']
else:
 f=Path(tempfile.mkdtemp(prefix='original-codesign-certificate-',dir=r/'runtime'));f.chmod(0o700)
 def openssl(*args):
  subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if a.imported_store:
  assert a.certificate
  imported=(r/a.imported_store).resolve(strict=True);assert imported.is_relative_to(r/'runtime') and not imported.stat().st_mode&0o077
  shutil.copy2(imported,f/'identity-store.plist');shutil.copy2(r/a.certificate,f/'certificate.pem')
 else:
  assert not a.certificate
  openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(f/'key.pem'),'-out',str(f/'certificate.pem'),'-subj','/CN=Linuxcode Temporary Code Signing Fixture','-days','2','-addext','basicConstraints=critical,CA:FALSE','-addext','keyUsage=critical,digitalSignature','-addext','extendedKeyUsage=codeSigning')
 openssl('x509','-in',str(f/'certificate.pem'),'-outform','DER','-out',str(f/'certificate.der'))
 if not a.imported_store:
  openssl('rsa','-in',str(f/'key.pem'),'-traditional','-outform','DER','-out',str(f/'key.der'))
  store=f/'identity-store.plist';store.write_bytes(plistlib.dumps(dict(version=1,locked=False,items=[dict(label='fixture',certificate=(f/'certificate.der').read_bytes(),privateKey=(f/'key.der').read_bytes())])));store.chmod(0o600)
 for name in ['key.pem','key.der','certificate.pem','certificate.der']:
  if (f/name).exists():(f/name).chmod(0o600)
 if a.unified:
  original=(r/a.small_binary).resolve(strict=True);assert original.is_relative_to(r/'runtime')
  assert original.read_bytes()[:8]==bytes.fromhex('cffaedfe07000001'), 'expected an Intel Mach-O'
  app=f/'SameOwnerSmoke.app';executable=app/'Contents/MacOS/SameOwnerSmoke';executable.parent.mkdir(parents=True)
  shutil.copy2(original,executable);executable.chmod(0o755)
  (app/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='org.linuxcode.same-owner-smoke',CFBundleExecutable='SameOwnerSmoke',CFBundleName='SameOwnerSmoke',CFBundlePackageType='APPL',CFBundleVersion='1',CFBundleShortVersionString='1.0')))
 else:
  original=r/'runtime/ios-cocoapods-build/DerivedData/Build/Products/Debug-iphoneos/iOSCocoaPodsSmoke.app'
  app=f/'iOSCocoaPodsSmoke.app';shutil.copytree(original,app)
 identity=hashlib.sha1((f/'certificate.der').read_bytes()).hexdigest().upper()
 args=['/usr/bin/codesign','--force','--sign',identity,'--timestamp=none','--verbose=4',guest(app)]
 script=f/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\nprintf "CERTIFICATE_CODESIGN_BEGIN\\n"\n'+shlex.join(args)+'\ns=$?\nprintf "CERTIFICATE_CODESIGN_SIGN_STATUS %s\\n" "$s"\nif [ "$s" -ne 0 ]; then exit "$s"; fi\n'+shlex.join(['/usr/bin/codesign','--verify','--strict','--verbose=4',guest(app)])+'\ns=$?\nprintf "CERTIFICATE_CODESIGN_VERIFY_STATUS %s\\n" "$s"\nexit "$s"\n')
 setup=dict(stage=a.stage,configuration=a.configuration,identity_SHA1=identity,public_certificate_SHA256=sha(f/'certificate.der'),application=str(app.relative_to(r)),temporary_self_generated_identity_only=not a.imported_store or a.synthetic_test_identity,caller_provided_identity=bool(a.imported_store),certificate_chain_or_device_trust_verified=False,private_material_not_for_publication=True)
 if a.unified:setup.update(stage=None,configuration=None,unified_runtime=True,common_security_build=a.common_security_build,common_security_build_sha256=sha(r/a.common_security_build),original_small_binary=str(original.relative_to(r)),original_small_binary_sha256=sha(original),native_execution_attempted=False)
 if a.unified and a.preflight_binary:
  preflight=(r/a.preflight_binary).resolve(strict=True);assert preflight.is_relative_to(r/'runtime')
  setup.update(preflight_only=a.preflight_only,preflight_binary=str(preflight.relative_to(r)),preflight_binary_sha256=sha(preflight))
  invocation=shlex.join([guest(preflight),guest(f/'preflight.cms')])+'\ns=$?\nprintf "CERTIFICATE_PREFLIGHT_STATUS %s\\n" "$s"\n'
  if a.preflight_only:script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+invocation+'exit "$s"\n')
  else:script.write_text(script.read_text().replace('printf "CERTIFICATE_CODESIGN_BEGIN',invocation+'if [ "$s" -ne 0 ]; then exit "$s"; fi\nprintf "CERTIFICATE_CODESIGN_BEGIN',1))
 (f/'prepared.json').write_text(json.dumps(setup,indent=2)+'\n')
if a.prepare_only:
 print('PREPARED',f.relative_to(r));raise SystemExit(0)
assert not (f/'result.json').exists()
if a.unified:
 config=json.loads((r/a.configuration).read_text());assert config['runtime_mode']=='unified'
 launcher_path=config['run_launcher_stage'];launcher=json.loads((r/launcher_path).read_text())
 assert sha(r/launcher_path)==config['run_launcher_stage_sha256'] and launcher['run_environment_shared_from_bootstrap']
 assert launcher.get('materialized_shared_runtime'), 'require the common whole-run image before first launchd'
 build_path=setup['common_security_build'];assert sha(r/build_path)==setup['common_security_build_sha256']
 build=json.loads((r/build_path).read_text());assert build['host_verified'] and not build['old_security_backend_loaded']
 m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=a.stage,configuration=a.configuration)
 assert profile['direct_resource_environment']['runtime_mode']=='unified'
 cmd=list(profile['command'][:-2]);assert not any(v.startswith('DARLING_DYLD_OVERRIDE_') for v in cmd)
 expected=sha(r/build['framework']);selected=None
 for directory in profile['direct_resource_environment']['tool_environment']['DYLD_FRAMEWORK_PATH'].split(':'):
  candidate=Path(directory.replace('/Volumes/SystemRoot/workspace',str(r)))/'Security.framework/Versions/A/Security'
  if candidate.is_file():selected=candidate;break
 assert selected is not None and sha(selected)==expected, 'common Security candidate must already be selected by the public configuration'
 # Identity is a business input. Library paths and service environments are never changed.
 store_arg='LINUXCODE_IDENTITY_STORE='+guest(f/'identity-store.plist')
 positions=[i for i,v in enumerate(cmd) if v.startswith('LINUXCODE_IDENTITY_STORE=')]
 assert len(positions)<=1
 if positions:cmd[positions[0]]=store_arg
 else:cmd.append(store_arg)
 cmd+=['/bin/bash',guest(f/'run.sh')];cmd[3]='120'
 if setup.get('preflight_binary'):assert sha(r/setup['preflight_binary'])==setup['preflight_binary_sha256']
 env=m['environment'](profile);log=f/'run.log'
 print('RUNNING_UNIFIED',f.relative_to(r),flush=True)
 with log.open('w') as out:result=subprocess.run(cmd,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
 text=log.read_text();signed=re.findall(r'^CERTIFICATE_CODESIGN_SIGN_STATUS (\d+)$',text,re.M);verified=re.findall(r'^CERTIFICATE_CODESIGN_VERIFY_STATUS (\d+)$',text,re.M)
 record=dict(**setup,executed_stage=a.stage,executed_stage_sha256=sha(r/a.stage),executed_configuration=a.configuration,executed_configuration_sha256=sha(r/a.configuration),command=cmd,shared_tool_environment=profile['direct_resource_environment']['tool_environment'],common_security_sha256=expected,common_security_selected=str(selected.relative_to(r)),run_launcher_stage=launcher_path,outer_status=result.returncode,native_sign_status=signed,native_verify_status=verified,original_codesign_frontend_completed=result.returncode==0 and signed==['0'] and verified==['0'],CMS_cryptography_independently_verified=False,source_sha256=sha(Path(__file__)),log=str(log.relative_to(r)),log_sha256=sha(log),full_UE_revalidation=False,daemon_library_paths_modified=False)
 record['native_execution_attempted']=True
 if setup.get('preflight_binary'):
  assert sha(r/setup['preflight_binary'])==setup['preflight_binary_sha256']
  record['native_preflight_status']=re.findall(r'^CERTIFICATE_PREFLIGHT_STATUS (\d+)$',text,re.M)
  record['preflight_completed']=result.returncode==0 and record['native_preflight_status']==['0'] and 'CERTIFICATE_PREFLIGHT CMS_WRITTEN ' in text
  record['preflight_API_statuses']=re.findall(r'^CERTIFICATE_PREFLIGHT ([a-z-]+) (-?\d+)$',text,re.M)
 (f/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-4500:]);print('EVIDENCE',f/'result.json')
 raise SystemExit(0 if (record.get('preflight_completed',False) if setup.get('preflight_only') else record['original_codesign_frontend_completed']) else 1)
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
