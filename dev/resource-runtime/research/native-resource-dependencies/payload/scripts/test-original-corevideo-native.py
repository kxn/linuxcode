#!/usr/bin/env python3
"""Check original CPU pixel buffers, attachment objects and release callbacks."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--graphics-stage',required=True)
args=parser.parse_args()
folder=Path(tempfile.mkdtemp(prefix='original-corevideo-native-test-',dir=root/'runtime'))
source=root/'fixtures/hello/original-corevideo-native.c'
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
obj,binary=folder/'test.o',folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreVideo','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
p=module['profile'](graphics_stage=args.graphics_stage,include_resource_environment=False)
env=module['environment'](p)
gui=['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
for name in gui:env.pop(name,None)
command=p['command'][:-2]+['/usr/bin/env',*[part for name in gui for part in ('-u',name)],'/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))]
command[3]='60'
log=folder/'run.log'
with log.open('w') as stream:result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
text=log.read_text()
markers=['ORIGINAL_COREVIDEO_CPU_PIXEL_BYTES_STRIDE_AND_OWNERSHIP_OK 3','ORIGINAL_COREVIDEO_ATTACHMENT_TYPE_RETENTION_AND_REMOVAL_OK 3']
verified=result.returncode==0 and all(re.search('^'+re.escape(marker)+'$',text,re.M) for marker in markers)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
record=dict(verified=bool(verified),outer_status=result.returncode,command=command,graphics_stage=args.graphics_stage,
    cpu_pixel_buffer_cases=3 if verified else 0,pixel_data_and_padding_preserved=bool(verified),
    files={str(p.relative_to(root)):sha(p) for p in [source,Path(__file__),binary,log,root/args.graphics_stage]},
    gui_environment_removed=gui,full_CoreVideo_API_verified=False,full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-3000:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
