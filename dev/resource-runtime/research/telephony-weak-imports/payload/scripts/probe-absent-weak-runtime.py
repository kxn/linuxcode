#!/usr/bin/env python3
"""Check real Darling weak absence, provider presence and strong-load rejection."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import shlex
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage',required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='absent-weak-runtime-',dir=root/'runtime'))
available = folder/'available';available.mkdir()
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
guest = root/'runtime/rootfs/usr/libexec/darling'
source = root/'fixtures/hello/absent-weak.c'
optional = '/linuxcode-unavailable-weak-test/libLinuxcodeOptionalValue.dylib'
for mode in ['provider','caller','strong-caller']:
    subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2',
        *(['-DLINUXCODE_OPTIONAL_PROVIDER'] if mode=='provider' else
          ['-DLINUXCODE_REQUIRED_PROVIDER'] if mode=='strong-caller' else []),'-c',str(source),
        '-o',str(folder/(mode+'.o'))],check=True)
link = ['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11',
    '-syslibroot',str(guest),'-L',str(guest/'usr/lib'),'-lSystem']
provider = available/'libLinuxcodeOptionalValue.dylib'
subprocess.run([*link,'-dylib','-install_name',optional,str(folder/'provider.o'),'-o',str(provider)],check=True)
for mode,option in [('weak','-weak_library'),('strong','-needed_library')]:
    obj=folder/('strong-caller.o' if mode=='strong' else 'caller.o')
    subprocess.run([*link,option,str(provider),str(obj),'-o',str(folder/mode)],check=True)
    data=(folder/mode).read_bytes();at=32;loads=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,at)
        if command in (0xc,0x80000018):
            offset=struct.unpack_from('<I',data,at+8)[0]
            name=data[at+offset:data.index(0,at+offset)].decode()
            if name==optional:loads.append(command)
        at+=size
    assert loads==([0x80000018] if mode=='weak' else [0xc])
module=runpy.run_path(str(root/'scripts/private-procfs-runtime-profile.py'))
p=module['profile'](stage=args.stage)
sha=lambda name:hashlib.sha256((root/name).read_bytes()).hexdigest()
cases=[]
for mode in ['weak-absent','weak-present','strong-absent']:
    command=list(p['command'])
    if mode=='weak-present':
        index=next(i for i,x in enumerate(command) if x.startswith('DYLD_LIBRARY_PATH='))
        command[index]='DYLD_LIBRARY_PATH=/Volumes/SystemRoot/workspace/'+str(available.relative_to(root))+':'+command[index].split('=',1)[1]
    executable=folder/('strong' if mode=='strong-absent' else 'weak')
    script=folder/(mode+'.sh')
    script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+
        shlex.join(['/Volumes/SystemRoot/workspace/'+str(executable.relative_to(root)),
                    '1' if mode=='weak-present' else '0'])+
        '\nstatus=$?\nprintf "ABSENT_WEAK_STATUS %s\\n" "$status"\nexit "$status"\n')
    command=command[:-2]+['/bin/bash','/Volumes/SystemRoot/workspace/'+str(script.relative_to(root))]
    command[3]='60';environment=module['environment'](p)
    for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:environment.pop(name,None)
    log=folder/(mode+'.log')
    with log.open('w') as stream:result=subprocess.run(command,cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT)
    text=log.read_text();statuses=re.findall(r'^ABSENT_WEAK_STATUS (\d+)$',text,re.M)
    if mode=='strong-absent':
        verified=(result.returncode!=0 and statuses!=['0'] and 'ABSENT_WEAK_MAIN_ENTERED' not in text
                  and optional in text and 'Library not loaded:' in text)
    else:
        marker='WEAK_PROVIDER_PRESENT_REAL_FUNCTION_OK' if mode=='weak-present' else 'WEAK_PROVIDER_ABSENT_NULL_REFERENCE_OK'
        verified=result.returncode==0 and statuses==['0'] and marker in text
    cases.append(dict(mode=mode,verified=bool(verified),outer_status=result.returncode,
        native_status=statuses,command=command,log=str(log.relative_to(root)),log_sha256=sha(log.relative_to(root))))
    print(mode,bool(verified),text[-1000:],flush=True)
record=dict(verified=all(case['verified'] for case in cases),cases=cases,stage=args.stage,
    sources={name:sha(name) for name in ['scripts/probe-absent-weak-runtime.py','fixtures/hello/absent-weak.c']},
    framework_API_implemented=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
