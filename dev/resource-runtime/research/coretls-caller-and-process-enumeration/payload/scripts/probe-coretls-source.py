#!/usr/bin/env python3
"""Validate both factories by generating real TLS1.2 ClientHello messages."""
from pathlib import Path
import argparse,hashlib,json,re,runpy,shlex,subprocess,tempfile
r=Path(__file__).resolve().parent.parent;p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-report',required=True);p.add_argument('--stage',required=True);p.add_argument('--configuration',required=True);a=p.parse_args()
folder=Path(tempfile.mkdtemp(prefix='coretls-native-',dir=r/'runtime'));build=json.loads((r/a.build_report).read_text());sdk=r/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';repo=r/'vendor/darling/src/external/coretls'
source=r/'fixtures/hello/coretls-caller-clienthello.c';obj=folder/'test.o';binary=folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-std=gnu99','-isysroot',str(sdk),'-I',str(repo/'lib'),'-O1','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(r/'scripts/direct-resource-tool-runtime-profile.py'));profile=module['profile'](stage=a.stage,configuration=a.configuration)
scope=profile['direct_resource_environment']['tool_environment'];command=list(profile['command'])
for key in ['DYLD_LIBRARY_PATH','DYLD_FRAMEWORK_PATH']:
    index=next(i for i,v in enumerate(command) if v.startswith(key+'='));command[index]=key+'='+scope[key]
profile={**profile,'command':command};profile=runpy.run_path(str(r/'scripts/coretls-source-runtime-profile.py'))['select'](profile,a.build_report)
symbols=folder/'symbols.txt';names=sorted(set(re.findall(r'^0x[\da-fA-F]+\s+(\S+)',subprocess.check_output(['llvm-objdump-19','--macho','--exports-trie',str(r/build['backend'])],text=True),re.M)));assert len(names)==301;symbols.write_text('\n'.join(names)+'\n')
guest=lambda path:'/Volumes/SystemRoot/workspace/'+str(path.relative_to(r));script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+shlex.join([guest(binary),guest(symbols)])+'\ns=$?\nprintf "CORETLS_SOURCE_STATUS %s\\n" "$s"\nexit "$s"\n');command=profile['command'][:-2]+['/bin/bash',guest(script)];command[3]='70'
log=folder/'run.log';print('RUNNING',folder.relative_to(r),flush=True)
with log.open('w') as out:result=subprocess.run(command,cwd=r,env=module['environment'](profile),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();statuses=re.findall(r'^CORETLS_SOURCE_STATUS (\d+)$',text,re.M);verified=result.returncode==0 and statuses==['0'] and 'CORETLS_CALLER_AND_LEGACY_REAL_TLS12_CLIENTHELLO_AND_MALFORMED_REJECTION_OK' in text
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();record=dict(verified=verified,build_report=a.build_report,build_report_sha256=sha(r/a.build_report),stage=a.stage,configuration=a.configuration,command=command,outer_status=result.returncode,native_status=statuses,log=str(log.relative_to(r)),log_sha256=sha(log),source_sha256=sha(source),binary_sha256=sha(binary),scope='Four caller labels and legacy factory generate real TLS1.2 ClientHello with an explicitly selected suite; malformed ServerHello rejected',completed_TLS_handshake_or_certificate_trust_verified=False,UE_build_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-1800:]);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
