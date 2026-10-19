#!/usr/bin/env python3
"""Validate original TCC/Accounts/SharedFileList CFString objects and copied values."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--graphics-stage',required=True)
parser.add_argument('--runtime-profile',default='scripts/coregraphics-native-security-profile.py')
parser.add_argument('--stage',default='artifacts/ios-resource-lazy-v1-stage.json')
args=parser.parse_args()
folder=Path(tempfile.mkdtemp(prefix='original-resource-identifiers-',dir=root/'runtime'))
cache=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
pins=json.loads((root/'config/coregraphics-image-pins.json').read_text())
graphics=json.loads((root/args.graphics_stage).read_text())
frameworks=Path(graphics['library']).parents[3]
targets=[('tcc-resource-native','_kTCCServiceSystemPolicyAppData'),
         ('accounts-resource-native','_ACAccountTypeIdentifierGameCenter'),
         ('sharedfilelist-resource-native','_kLSSharedFileListFinderProjectsItems')]
cases=[];arguments=[]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for target,symbol in targets:
    pin=pins[target];path=pin['path'];original=root/('runtime/fullsystem-libraries'+path)
    assert sha(original)==pin['sha256']
    address=cache['resolve'](path,symbol);assert address
    object_address=cache['pointer'](address)
    flags=struct.unpack('<I',cache['read'](object_address+8,4))[0]
    length=struct.unpack('<Q',cache['read'](object_address+24,8))[0]
    assert flags&255==0xc8 and 0<length<4096
    chars=cache['pointer'](object_address+16)
    expected=cache['read'](chars,length).decode('ascii')
    name=Path(path).name
    selected=frameworks/(name+'.framework/Versions/A/'+name)
    guest='/Volumes/SystemRoot/workspace/'+str(selected)
    cases.append(dict(target=target,symbol=symbol,expected=expected,original_sha256=pin['sha256'],
        global_address=hex(address),cfstring_flags=hex(flags),selected=str(selected),selected_sha256=sha(root/selected)))
    arguments.extend([guest,symbol[1:],expected])
source=root/'fixtures/hello/original-resource-identifiers.c'
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
obj,binary=folder/'test.o',folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-framework','CoreFoundation','-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(root/args.runtime_profile))
p=module['profile'](stage=args.stage,graphics_stage=args.graphics_stage,include_resource_environment=True)
env=module['environment'](p)
gui=['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
for name in gui:env.pop(name,None)
command=p['command'][:-2]+['/usr/bin/env',*[part for name in gui for part in ('-u',name)],
    '/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root)),*arguments]
command[3]='60'
log=folder/'run.log'
with log.open('w') as stream:result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
text=log.read_text()
verified=result.returncode==0 and re.search(r'^ORIGINAL_RESOURCE_IDENTIFIERS_NATIVE_OK 3$',text,re.M) is not None
record=dict(verified=verified,outer_status=result.returncode,command=command,cases=cases,
    original_values_from_pinned_cache=True,CF_types_and_copy_independence_verified=verified,
    GUI_environment_removed=gui,full_framework_API_verified=False,resource_compilation_verified=False,
    files={str(p.relative_to(root)):sha(p) for p in [source,Path(__file__),binary,log,root/args.graphics_stage,root/args.stage]})
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-3000:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
