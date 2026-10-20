#!/usr/bin/env python3
"""Reproduce the two-level, two-marker, zero-emitted-requirement environment."""
from pathlib import Path
import hashlib
import json
import re
import runpy
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
module = runpy.run_path(str(root/'scripts/xcode-tool-dispatch-runtime-profile.py'))
profile = module['profile']()
folder = Path(tempfile.mkdtemp(prefix='original-swift-nested-marker-',dir=root/'runtime'))
for name in ['NestedMarker.swift','main.swift']:
    shutil.copy2(root/'fixtures/SwiftNestedMarkerEnvironment'/name,folder/name)
guest = '/Volumes/SystemRoot/workspace/'+str(folder.relative_to(root))+'/'
compiler = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc'
common = ['-module-name','NestedMarker','-target','x86_64-apple-macosx15.0','-sdk',
    '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk']
commands = [('IR',[compiler,guest+'NestedMarker.swift','-emit-ir',*common,'-o',guest+'NestedMarker.ll']),
    ('COMPILE',[compiler,guest+'NestedMarker.swift',guest+'main.swift',*common,'-o',guest+'KeyPathSmoke']),
    ('RUN',[guest+'KeyPathSmoke'])]
script = folder/'run.sh'
script.write_text('#!/bin/bash\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n'+''.join(
    shlex.join(argv)+'\nstatus=$?\nprintf "NESTED_MARKER_'+name+'_STATUS %s\\n" "$status"\n'
    'if [ "$status" -ne 0 ]; then exit "$status"; fi\n' for name,argv in commands))
command = profile['command'][:-2]+['/bin/bash',guest+'run.sh']
command[3] = '180'
log = folder/'run.log'
with log.open('w') as stream:
    result = subprocess.run(command,cwd=root,env=module['environment'](profile),
        stdout=stream,stderr=subprocess.STDOUT)
text = log.read_text()
ir = folder/'NestedMarker.ll'
lines = [line for line in ir.read_text().splitlines() if line.startswith('@"generic environment ')] if ir.exists() else []
expected = '<{ i32 8194, i16 1, i16 2, i8 -128, i8 -128, [2 x i8] zeroinitializer }>'
matched = [line for line in lines if expected in line]
verified = result.returncode == 0 and len(matched) == 1 and all(
    re.search('^NESTED_MARKER_'+name+'_STATUS 0$',text,re.M) for name,_ in commands)
verified = verified and bool(re.search('^ORIGINAL_SWIFT_NESTED_MARKER_KEYPATH_OK 2$',text,re.M))
files = [script,log,folder/'NestedMarker.swift',folder/'main.swift',Path(__file__),
    root/('runtime/state/prefix'+compiler),*[p for p in [ir,folder/'KeyPathSmoke'] if p.exists()]]
record = dict(verified=bool(verified),outer_status=result.returncode,command=command,
    original_Apple_compiler_used=True,original_metadata_edited=False,IR_environment_lines=lines,
    matching_environment_lines=matched,native_KeyPath_projections=2 if verified else 0,
    declared_requirements=2 if verified else None,emitted_requirements=0 if verified else None,
    generic_levels=2 if verified else None,
    files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    TextRecognition_runtime_verified=False,resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-1800:]);print('IR',lines);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
