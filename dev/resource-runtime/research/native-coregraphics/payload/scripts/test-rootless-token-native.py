#!/usr/bin/env python3
"""Compare deferred entry points to native backend calls after libSystem init."""
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
folder=Path(tempfile.mkdtemp(prefix='rootless-token-native-test-',dir=root/'runtime'))
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=root/'fixtures/hello/rootless-token-native.c'
obj,binary=folder/'test.o',folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
m=runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
p=m['profile'](graphics_stage=args.graphics_stage,include_resource_environment=False)
env=m['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
command=p['command'][:-2]+['/usr/bin/env','-u','DISPLAY','-u','WAYLAND_DISPLAY','-u','XAUTHORITY','/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))]
command[3]='60';log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();verified=result.returncode==0 and bool(re.search('^NATIVE_ROOTLESS_TOKEN_DEFERRED_FORWARDING_AND_REAL_RESULT_BITS_OK 155$',text,re.M))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
record=dict(verified=verified,outer_status=result.returncode,command=command,source_sha256=sha(source),test_driver_sha256=sha(__file__),binary_sha256=sha(binary),graphics_stage=args.graphics_stage,graphics_stage_sha256=sha(root/args.graphics_stage),log=str(log.relative_to(root)),log_sha256=sha(log),platform_trust_enforcement_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-2200:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
