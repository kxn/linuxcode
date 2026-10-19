#!/usr/bin/env python3
"""Reproduce original Swift environment inverse-record emission and execution."""
from pathlib import Path
import hashlib
import json
import re
import runpy
import shlex
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
module=runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'))
profile=module['profile']()
folder=Path(tempfile.mkdtemp(prefix='original-swift-inverse-environment-',dir=root/'runtime'))
for name in ['InverseKeyPath.swift','main.swift']:
    shutil.copy2(root/'fixtures/SwiftInverseEnvironment'/name,folder/name)
guest='/Volumes/SystemRoot/workspace/'+str(folder.relative_to(root))+'/'
compiler='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc'
common=['-module-name','InverseKeyPath','-target','x86_64-apple-macosx15.0','-sdk','/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
commands=[('IR',[compiler,guest+'InverseKeyPath.swift','-emit-ir',*common,'-o',guest+'InverseKeyPath.ll']),
          ('COMPILE',[compiler,guest+'InverseKeyPath.swift',guest+'main.swift',*common,'-o',guest+'InverseKeyPathSmoke']),
          ('RUN',[guest+'InverseKeyPathSmoke'])]
script=folder/'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\n'+''.join(shlex.join(argv)+'\nstatus=$?\nprintf "ORIGINAL_SWIFT_INVERSE_'+name+'_STATUS %s\\n" "$status"\nif [ "$status" -ne 0 ]; then exit "$status"; fi\n' for name,argv in commands))
command=profile['command'][:-2]+['/usr/bin/env','-u','DISPLAY','-u','WAYLAND_DISPLAY','-u','XAUTHORITY','/bin/bash',guest+'run.sh'];command[3]='180'
environment=module['environment'](profile)
for key in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:environment.pop(key,None)
log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=environment,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text()
valid=result.returncode==0 and all(re.search('^ORIGINAL_SWIFT_INVERSE_'+name+'_STATUS 0$',text,re.M) for name,_ in commands) and bool(re.search('^ORIGINAL_SWIFT_INVERSE_ENVIRONMENT_KEYPATH_PROJECTIONS_OK 6$',text,re.M))
ir=folder/'InverseKeyPath.ll'
lines=[]
if ir.exists():
    lines=[line for line in ir.read_text().splitlines() if line.startswith('@"generic environment ') and 'BufferRepresentable' in line]
    valid=valid and len(lines)==1
    if lines:
        # Flags/count/parameter/padding + two 12-byte requirement records.
        signature=re.search(r'constant <\{ (.*?) \}>',lines[0])
        valid=valid and signature is not None and signature[1].split(', ')==['i32','i16','i8','[1 x i8]',*(['i32']*5),'i16','i16']
        valid=valid and bool(re.search(r'<\{ i32 4097, i16 1, i8 -128,',lines[0]))
        valid=valid and bool(re.search(r'i32 5, i32 .*?, i16 0, i16 1 \}>',lines[0]))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
files=[script,log,folder/'InverseKeyPath.swift',folder/'main.swift',Path(__file__),root/('runtime/state/prefix'+compiler)]
files += [p for p in [ir,folder/'InverseKeyPathSmoke'] if p.exists()]
record=dict(verified=bool(valid),outer_status=result.returncode,original_Apple_compiler_used=True,original_metadata_edited=False,
            declared_requirements=1 if valid else None,emitted_requirements=2 if valid else None,
            native_KeyPath_projections=6 if valid else 0,IR_environment_lines=lines,command=command,
            files={str(p.relative_to(root)):sha(p) for p in files},full_CoreVideo_API_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-2200:]);print('IR',lines);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if valid else 1)
