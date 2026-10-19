#!/usr/bin/env python3
"""Validate actual PNG pixels and color conversion in separate native processes."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--graphics-stage', required=True)
args = parser.parse_args()
folder = Path(tempfile.mkdtemp(prefix='original-cg-images-test-',dir=root/'runtime'))
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source = root/'fixtures/hello/original-coregraphics-images.c'
obj, binary = folder/'test.o',folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos15','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','15','15','-syslibroot',str(sdk),'-framework','CoreGraphics','-framework','ImageIO','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
fixture = json.loads((root/'artifacts/imageio-input-fixtures.json').read_text())[0]
assert sha(root/fixture['path'])==fixture['sha256']
m = runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
p = m['profile'](graphics_stage=args.graphics_stage,include_resource_environment=False)
env = m['environment'](p)
gui = ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
for name in gui: env.pop(name,None)
records=[]
for case, marker in [('png','ORIGINAL_CG_NATIVE_PNG_91_PIXELS_INDEPENDENTLY_MATCHED'),('color','ORIGINAL_CG_NATIVE_COLOR_CONVERSION_MATCHES_INDEPENDENT_SRGB_FORMULA')]:
    command = p['command'][:-2]+['/usr/bin/env',*[part for name in gui for part in ('-u',name)],'/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root)),case]
    command[3]='60'
    log=folder/(case+'.log')
    with log.open('w') as out: result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text(); valid=result.returncode==0 and bool(re.search('^'+marker+'$',text,re.M))
    records.append(dict(case=case,verified=valid,outer_status=result.returncode,command=command,log=str(log.relative_to(root)),log_sha256=sha(log)))
    print(case,valid,text[-2200:],flush=True)
record=dict(verified=all(row['verified'] for row in records),cases=records,source_sha256=sha(source),test_driver_sha256=sha(__file__),binary_sha256=sha(binary),graphics_stage=args.graphics_stage,graphics_stage_sha256=sha(root/args.graphics_stage),fixture=fixture,gui_environment_removed=gui,full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if record['verified'] else 1)
