#!/usr/bin/env python3
"""Add five actual uint32 sandbox flag objects, preserving existing libSystem exports."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct
import subprocess

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag',required=True)
parser.add_argument('--base-stage',required=True)
args=parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder=root/('runtime/native-sandbox-extension-constants-'+args.tag)
output=root/('artifacts/native-sandbox-extension-constants-'+args.tag+'-stage.json')
assert not folder.exists() and not output.exists()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
base=json.loads((root/args.base_stage).read_text())
for path,expected in base['files'].items():
    if path.startswith(('config/','scripts/','vendor/')):resolve(path,expected)
    else:assert sha(path)==expected,path
cache=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
provider='/usr/lib/system/libsystem_sandbox.dylib'
pin=json.loads((root/'config/cache-image-pins.json').read_text())['sandbox-native']
original='runtime/fullsystem-libraries'+provider
assert sha(original)==pin['sha256']
names=['SANDBOX_EXTENSION_NOFOLLOW','SANDBOX_EXTENSION_NOFOLLOW_ANY',
       'SANDBOX_EXTENSION_NO_STORAGE_CLASS','SANDBOX_EXTENSION_USER_INTENT','SANDBOX_EXTENSION_MACL_LEARNING']
values={name:struct.unpack('<I',cache['read'](cache['resolve'](provider,'_'+name),4))[0] for name in names}
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source='vendor/darling/src/sandbox/extension_constants.c'
library=folder/'libraries/libSystem.B.dylib';library.parent.mkdir(parents=True)
helper=folder/'libraries/libDarlingSandboxExtensionConstants.dylib'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(root/source),'-o',str(folder/'constants.o')],check=True)
subprocess.run(['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem','-install_name','/usr/lib/'+helper.name,str(folder/'constants.o'),'-o',str(helper)],check=True)
symbols={p[2]:int(p[0],16) for line in subprocess.check_output(['llvm-nm-19','--defined-only',str(helper)],text=True).splitlines() if len(p:=line.split())==3}
data=helper.read_bytes();at=32;segments=[]
for _ in range(struct.unpack_from('<I',data,16)[0]):
    cmd,size=struct.unpack_from('<II',data,at)
    if cmd==25:
        vm,_,offset,length=struct.unpack_from('<4Q',data,at+24);segments.append((vm,offset,length))
    at+=size
for name,value in values.items():
    address=symbols['_'+name];assert address%4==0
    vm,offset,length=next(s for s in segments if s[0]<=address and address+4<=s[0]+s[2])
    assert struct.unpack_from('<I',data,offset+address-vm)[0]==value,name
payload,changes=runpy.run_path(str(root/'scripts/macho-named-reexport.py'))['add'](
    (root/base['library']).read_bytes(),'/usr/lib/'+helper.name,['_'+name for name in names])
library.write_bytes(payload)
files={**base['files'],**{p:sha(p) for p in [args.base_stage,original,source,
    'scripts/stage-native-sandbox-extension-constants.py',str(helper.relative_to(root)),str(library.relative_to(root))]}}
record=dict(library=str(library.relative_to(root)),helper=base['helper'],files=files,
    additional_libraries=[*base.get('additional_libraries',[]),str(helper.relative_to(root))],
    values=values,original_provider=provider,original_provider_sha256=sha(original),type='const uint32_t',
    source_bytes_equal_original=True,export_changes=changes,new_policy_operations_implemented=False,
    installed=False,runtime_execution_verified=False)
output.write_text(json.dumps(record,indent=2)+'\n');print(output.relative_to(root))
