#!/usr/bin/env python3
"""Start the packaged paired SecurityServer and observe a real absent-identity query."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,plistlib,runpy,subprocess,tempfile,re
r=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--codesign-stage',required=True);a=parser.parse_args()
m=runpy.run_path(str(r/'scripts/codesign-zsign-runtime-profile.py'));p=m['profile'](codesign_stage=a.codesign_stage)
w=Path(tempfile.mkdtemp(prefix='securityd-identity-store-',dir=r/'runtime'));guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r));sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';src=w/'query.c';src.write_text('''#include <CoreFoundation/CoreFoundation.h>
#include <Security/Security.h>
#include <stdio.h>
int main(void){setbuf(stdout,NULL);const void *keys[]={kSecClass,kSecAttrLabel,kSecMatchLimit,kSecReturnRef};const void *vals[]={kSecClassIdentity,CFSTR("linuxcode-absent-identity-namespace-probe-9ae3b9e1"),kSecMatchLimitOne,kCFBooleanTrue};CFDictionaryRef q=CFDictionaryCreate(NULL,keys,vals,4,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);CFTypeRef result=NULL;puts("SECURITYD_IDENTITY_QUERY_BEGIN");OSStatus status=SecItemCopyMatching(q,&result);printf("SECURITYD_IDENTITY_QUERY_RETURNED %d\\n",(int)status);if(result)CFRelease(result);CFRelease(q);return status==errSecItemNotFound||status==errSecNoSuchKeychain?0:1;}
''')
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(src),'-o',str(w/'query.o')],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','Security','-framework','CoreFoundation','-lSystem',str(w/'query.o'),'-o',str(w/'query')],check=True)
original_job=r/'runtime/rootfs/usr/libexec/darling/System/Library/LaunchDaemons/com.apple.securityd.plist';job=plistlib.loads(original_job.read_bytes());job['StandardOutPath']=job['StandardErrorPath']=guest(w/'securityd.log');job['EnvironmentVariables']={**job.get('EnvironmentVariables',{}),**{key:value for key,value in (v.split('=',1) for v in p['command'] if v.startswith(('DYLD_FRAMEWORK_PATH=','DYLD_LIBRARY_PATH=')))}};jobpath=w/'securityd.plist';jobpath.write_bytes(plistlib.dumps(job));jobpath.chmod(0o644)
script=w/'run.sh';script.write_text('#!/bin/bash\nset -x\nset -e\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\nlaunchctl remove com.apple.securityd || true\nlaunchctl load '+guest(jobpath)+'\nlaunchctl start com.apple.securityd\nlaunchctl list com.apple.securityd\nprintf "SECURITYD_PAIRED_JOB_REQUESTED\\n"\n'+guest(w/'query')+'\nstatus=$?\nprintf "SECURITYD_IDENTITY_PROBE_STATUS %s\\n" "$status"\nexit "$status"\n')
command=p['command'][:-2]+['/bin/bash',guest(script)];command[3]='90';env=m['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
log=w/'run.log'
with log.open('w') as out:res=subprocess.run(command,cwd=r,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall('^SECURITYD_IDENTITY_QUERY_RETURNED (-?[0-9]+)$',text,re.M);valid=res.returncode==0 and len(statuses)==1 and int(statuses[0]) in [-25300,-25294]
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),verified=valid,outer_status=res.returncode,actual_identity_query_status=statuses,command=command,codesign_stage=a.codesign_stage,source_runtime=p['source_runtime'],original_securityd_sha256=sha(r/'runtime/rootfs/usr/libexec/darling/usr/sbin/securityd'),files={str(path.relative_to(r)):sha(path) for path in [src,script,jobpath,log]},source_driver_sha256=sha(__file__),actual_credentials_or_certificates_queried=False,expected_query_is_unique_absent_label=True,certificate_signing_ready=False)
if (w/'securityd.log').exists():record['files'][str((w/'securityd.log').relative_to(r))]=sha(w/'securityd.log')
(w/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-4000:]);print('EVIDENCE',w/'result.json');raise SystemExit(0 if valid else 1)
