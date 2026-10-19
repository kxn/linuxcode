#!/usr/bin/env python3
"""Compile real accessible-function records with Apple Swift and execute local calls."""
from pathlib import Path
import hashlib
import json
import re
import runpy
import shlex
import shutil
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
folder=Path(tempfile.mkdtemp(prefix='original-swift-accessible-functions-',dir=root/'runtime'))
source=root/'fixtures/SwiftAccessibleFunctions/AccessibleFunctions.swift'
shutil.copy2(source,folder/source.name)
guest='/Volumes/SystemRoot/workspace/'+str(folder.relative_to(root))+'/'
compiler='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc'
common=['-parse-as-library','-module-name','AccessibleFunctionsSmoke','-target','x86_64-apple-macosx15.0',
    '-sdk','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
commands=[('IR',[compiler,guest+source.name,'-emit-ir',*common,'-o',guest+'AccessibleFunctions.ll']),
    ('COMPILE',[compiler,guest+source.name,*common,'-o',guest+'AccessibleFunctionsSmoke']),
    ('RUN',[guest+'AccessibleFunctionsSmoke'])]
script=folder/'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n'+''.join(shlex.join(command)+'\nstatus=$?\nprintf "ORIGINAL_ACCESSIBLE_FUNCTION_'+label+'_STATUS %s\\n" "$status"\nif [ "$status" -ne 0 ]; then exit "$status"; fi\n' for label,command in commands))
module=runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'))
p=module['profile']()
env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
command=p['command'][:-2]+['/usr/bin/env','-u','DISPLAY','-u','WAYLAND_DISPLAY','-u','XAUTHORITY','/bin/bash',guest+'run.sh']
command[3]='180'
log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text()
native=result.returncode==0 and all(re.search('^ORIGINAL_ACCESSIBLE_FUNCTION_'+label+'_STATUS 0$',text,re.M) for label,_ in commands) and re.search(r'^ORIGINAL_ACCESSIBLE_FUNCTION_LOCAL_CALLS_OK 2$',text,re.M) is not None
records=[];binary=folder/'AccessibleFunctionsSmoke';ir=folder/'AccessibleFunctions.ll'
if native:
    data=binary.read_bytes();assert data[:4]==bytes.fromhex('cffaedfe')
    sections=[];segments=[];at=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,at)
        if cmd==25:
            vm,_,offset,length=struct.unpack_from('<4Q',data,at+24);segments.append((vm,offset,length))
            for index in range(struct.unpack_from('<I',data,at+64)[0]):
                slot=at+72+80*index;name=data[slot:slot+16].split(b'\0')[0].decode();segment=data[slot+16:slot+32].split(b'\0')[0].decode();address,length=struct.unpack_from('<QQ',data,slot+32);sections.append((segment,name,address,length))
        at+=size
    def read(address,length):
        for vm,offset,size in segments:
            if vm<=address and address+length<=vm+size:return data[offset+address-vm:offset+address-vm+length]
        raise ValueError('Original compiled input reference outside mapped file')
    records=runpy.run_path(str(root/'scripts/swift-accessible-function-records.py'))['validate'](read,sections)
    assert records and any(row['environment'] is not None for row in records)
    assert all(row['flags']==1 and row['async_context_size'] is not None for row in records)
    assert '__swift5_acfuncs' in ir.read_text()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
files=[source,Path(__file__),script,log,folder/source.name,root/('runtime/state/prefix'+compiler),root/'scripts/swift-accessible-function-records.py']
files.extend(p for p in [binary,ir] if p.exists())
record=dict(verified=bool(native and records),outer_status=result.returncode,command=command,
    original_Apple_compiler_used=True,native_local_distributed_calls=2 if native else 0,
    emitted_accessible_function_records=records,original_metadata_edited=False,
    remote_invocation_or_full_distributed_runtime_verified=False,
    files={str(p.relative_to(root)):sha(p) for p in files})
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-3200:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
