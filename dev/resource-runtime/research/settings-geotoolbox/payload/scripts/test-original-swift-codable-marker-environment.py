#!/usr/bin/env python3
"""Reproduce the actual four-declared/three-emitted standard protocol environment."""
from pathlib import Path
import hashlib,json,re,runpy,shlex,shutil,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
module=runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'));p=module['profile']()
folder=Path(tempfile.mkdtemp(prefix='original-swift-codable-marker-',dir=root/'runtime'))
for name in ['CodableMarker.swift','main.swift']:shutil.copy2(root/'fixtures/SwiftCodableMarkerEnvironment'/name,folder/name)
guest='/Volumes/SystemRoot/workspace/'+str(folder.relative_to(root))+'/'
compiler='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc'
common=['-module-name','CodableMarker','-target','x86_64-apple-macosx15.0','-sdk',
 '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
commands=[('IR',[compiler,guest+'CodableMarker.swift','-emit-ir',*common,'-o',guest+'CodableMarker.ll']),
 ('COMPILE',[compiler,guest+'CodableMarker.swift',guest+'main.swift',*common,'-o',guest+'KeyPathSmoke']),
 ('RUN',[guest+'KeyPathSmoke'])]
script=folder/'run.sh';script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+''.join(
 shlex.join(argv)+'\nstatus=$?\nprintf "CODABLE_MARKER_'+name+'_STATUS %s\\n" "$status"\nif [ "$status" -ne 0 ]; then exit "$status"; fi\n' for name,argv in commands))
command=p['command'][:-2]+['/bin/bash',guest+'run.sh'];command[3]='180';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=module['environment'](p),stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();ir=folder/'CodableMarker.ll'
lines=[line for line in ir.read_text().splitlines() if line.startswith('@"generic environment ')] if ir.exists() else []
matching=[line for line in lines if line.startswith('@"generic environment SeRzSERzSHRzs8SendableRzl"')]
expected=['i32','i16','i8','[1 x i8]']+['i32']*9
layout_ok=False
if len(matching)==1:
 match=re.search(r'constant <\{ (.*?) \}> <\{ i32 (\d+), i16 (\d+), i8 (-?\d+), \[1 x i8\] zeroinitializer,',matching[0])
 layout_ok=bool(match and match[1].split(', ')==expected and [int(match[i]) for i in [2,3,4]]==[16385,1,-128])
verified=result.returncode==0 and layout_ok and 'ORIGINAL_SWIFT_CODABLE_MARKER_KEYPATH_OK 12' in text and all(
 re.search('^CODABLE_MARKER_'+name+'_STATUS 0$',text,re.M) for name,_ in commands)
files=[script,log,folder/'CodableMarker.swift',folder/'main.swift',Path(__file__),root/('runtime/state/prefix'+compiler),
 *[f for f in [ir,folder/'KeyPathSmoke'] if f.exists()]]
report=dict(verified=bool(verified),outer_status=result.returncode,command=command,original_Apple_compiler_used=True,
 original_metadata_edited=False,IR_environment_lines=lines,matching_environment_lines=matching,
 declared_requirements=4 if layout_ok else None,emitted_requirements=3 if layout_ok else None,
 native_KeyPath_projections=12 if verified else 0,files={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
 HealthKit_runtime_verified=False,resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(text[-2500:]);print('IR',matching);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
