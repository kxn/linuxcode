#!/usr/bin/env python3
"""Exercise genuine original CG objects and bitmap output in the private runtime."""
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
folder = Path(tempfile.mkdtemp(prefix='original-cg-native-test-', dir=root/'runtime'))
source = root/'fixtures/hello/original-coregraphics-native.c'
sdk = root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
obj, binary = folder/'test.o', folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreGraphics','-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
module = runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
p = module['profile'](graphics_stage=args.graphics_stage, include_resource_environment=False)
env = module['environment'](p)
gui = ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
for name in gui: env.pop(name, None)
command = p['command'][:-2]+['/usr/bin/env',*[part for name in gui for part in ('-u',name)],'/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))]
command[3] = '60'
log = folder/'run.log'
with log.open('w') as out:
    result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
text = log.read_text()
markers = re.findall(r'^ORIGINAL_CG_NATIVE_(?:SIMD_LAYOUT_AND_VALUES|DEVICE_RGB|BITMAP_PIXELS_AND_IMAGE_DATA)_OK$',text,re.M)
verified = result.returncode == 0 and len(markers) == 3
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
record = dict(verified=verified, outer_status=result.returncode, markers=markers,
              command=command, graphics_stage=args.graphics_stage,
              graphics_stage_sha256=sha(root/args.graphics_stage),
              log=str(log.relative_to(root)), log_sha256=sha(log),
              source=str(source.relative_to(root)), source_sha256=sha(source),
              test_driver_sha256=sha(__file__), binary_sha256=sha(binary),
              gui_environment_removed=gui, full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-2800:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
