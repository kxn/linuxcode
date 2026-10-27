#!/usr/bin/env python3
"""Exercise rejection of an untrusted chain without explicit root anchors."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',required=True);p.add_argument('--candidate',required=True);p.add_argument('--external-developer',action='store_true');a=p.parse_args()
fixture=r/a.fixture;folder=Path(tempfile.mkdtemp(prefix='unanchored-identity-chain-',dir=r/'runtime'));folder.chmod(0o700)
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';source=r/'fixtures/hello/unanchored-identity-chain.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-Wno-deprecated-declarations','-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','Security','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
candidate=json.loads((r/a.candidate).read_text());m=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=m['profile'](stage=candidate['inputs']['stage']['path'],configuration=candidate['inputs']['configuration']['path']);signer=runpy.run_path(str(r/'scripts/native-certificate-runtime.py'));profile=signer['select'](profile,a.candidate,str((fixture/'imported/store.plist').relative_to(r)));jobs=profile['native_certificate_runtime'];guest=lambda n:'/Volumes/SystemRoot/workspace/'+str(n.relative_to(r))
script=folder/'run.sh';script.write_text('#!/bin/bash\nset -e\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\ntrap '+shlex.quote(jobs['cleanup'])+' EXIT\n'+jobs['startup']+shlex.join([guest(binary),guest(fixture/'imported/store.plist')]+(['external'] if a.external_developer else []))+'\n')
command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='90';log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as output:res=subprocess.run(command,cwd=r,env=m['environment'](profile),stdout=output,stderr=subprocess.STDOUT)
text=log.read_text();ok=res.returncode==0 and re.search(r'^UNANCHORED_TRUST_RETURN accepted=0 error=',text,re.M) is not None;sha=lambda n:hashlib.sha256(n.read_bytes()).hexdigest()
record=dict(verified=ok,outer_status=res.returncode,candidate=a.candidate,fixture=a.fixture,source_sha256=sha(source),command=command,log=str(log.relative_to(r)),log_sha256=sha(log),private_material_not_for_publication=True,system_trust_store_modified=False,Apple_developer_trust_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-3500:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if ok else 1)
