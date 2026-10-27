#!/usr/bin/env python3
"""Check actual native leaf-policy selection with private generated certificates."""
from pathlib import Path
import argparse,hashlib,json,plistlib,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--identity-stage',required=True);p.add_argument('--prepare-only',action='store_true');p.add_argument('--prepared-run');p.add_argument('--resource-scope',action='store_true');a=p.parse_args()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r))
if a.prepared_run:w=r/a.prepared_run
else:
 w=Path(tempfile.mkdtemp(prefix='local-identity-leaf-policy-',dir=r/'runtime'));w.chmod(0o700)
 def openssl(*args):subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 openssl('genrsa','-traditional','-out',str(w/'key.pem'),'2048');openssl('rsa','-in',str(w/'key.pem'),'-traditional','-outform','DER','-out',str(w/'key.der'))
 items=[]
 for label,ku,eku,extra,days in [('valid','digitalSignature','codeSigning','',2),('wrong-eku','digitalSignature','serverAuth','',2),('wrong-ku','keyEncipherment','codeSigning','',2),('unknown-critical','digitalSignature','codeSigning','1.2.3.4.5=critical,DER:01:01:FF\n',2),('expired','digitalSignature','codeSigning','',-1)]:
  ext=w/(label+'.cnf');ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,'+ku+'\nextendedKeyUsage='+eku+'\n'+extra)
  openssl('req','-new','-key',str(w/'key.pem'),'-subj','/CN=Linuxcode '+label,'-out',str(w/(label+'.csr')))
  validity=['-not_before','20000101000000Z','-not_after','20000102000000Z'] if days<0 else ['-days',str(days)]
  openssl('x509','-req','-in',str(w/(label+'.csr')),'-signkey',str(w/'key.pem'),*validity,'-extfile',str(ext),'-outform','DER','-out',str(w/(label+'.der')))
  items.append(dict(label=label,certificate=(w/(label+'.der')).read_bytes(),privateKey=(w/'key.der').read_bytes()))
 for name,locked in [('store.plist',False),('locked.plist',True)]:
  path=w/name;path.write_bytes(plistlib.dumps(dict(version=1,locked=locked,items=items)));path.chmod(0o600)
 for path in w.iterdir():path.chmod(0o600)
 sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
 src=r/'fixtures/hello/local-identity-policy.c';obj=w/'test.o';binary=w/'test'
 subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-Wno-deprecated-declarations','-c',str(src),'-o',str(obj)],check=True)
 subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','Security','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
if a.prepare_only:print('PREPARED',w.relative_to(r));raise SystemExit(0)
assert not (w/'result.json').exists()
m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage='artifacts/private-procfs-auditsession83-stage.json',configuration='config/direct-resource-tool-environment-v150.json');cmd=list(profile['command'][:-2])
if a.resource_scope:
 for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
  i=next(i for i,v in enumerate(cmd) if v.startswith(key+'='));cmd[i]=key+'='+profile['direct_resource_environment']['tool_environment'][key]
stage=json.loads((r/a.identity_stage).read_text())
for n,d in stage['files'].items():assert sha(r/n)==d,n
for name,leaf in [('DYLD_FRAMEWORK_PATH','frameworks'),('DYLD_LIBRARY_PATH','libraries')]:
 i=next(i for i,v in enumerate(cmd) if v.startswith(name+'='));cmd[i]=name+'='+guest(r/stage['root']/leaf)+':'+cmd[i].split('=',1)[1]
script=w/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(w/'test'),guest(w/'store.plist'),guest(w/'locked.plist')])+'\n')
cmd+=['/bin/bash',guest(script)];cmd[3]='60'
with (w/'run.log').open('w') as out:res=subprocess.run(cmd,cwd=r,env=m['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=(w/'run.log').read_text();ok=res.returncode==0 and 'LOCAL_IDENTITY_LEAF_POLICY_OK ' in text
record=dict(verified=ok,outer_status=res.returncode,identity_stage=a.identity_stage,log=str((w/'run.log').relative_to(r)),log_sha256=sha(w/'run.log'),source_sha256=sha(r/'fixtures/hello/local-identity-policy.c'),driver_sha256=sha(Path(__file__)),private_material_not_for_publication=True,chain_trust_or_provisioning_verified=False)
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-5000:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if ok else 1)
