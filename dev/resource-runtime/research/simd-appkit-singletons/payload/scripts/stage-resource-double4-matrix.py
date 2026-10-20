#!/usr/bin/env python3
"""Add a byte-checked SIMD constant to a new resource libSystem directory.

The full parent initializer/queue source library is retained. Only a named
reexport and its source-built constant provider are added; no existing export
payload or executable section is replaced.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--configuration',required=True)
parser.add_argument('--tag',required=True)
args=parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
folder=root/('runtime/resource-double4-matrix-'+args.tag)
assert not folder.exists()
config=json.loads((root/args.configuration).read_text())
base_path=config['resource_system_build']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/base_path)==config['resource_system_build_sha256']
base=json.loads((root/base_path).read_text())
assert base['full_initializer_and_queue_source_build'] and base['complete_source_files']==20
assert base['original_source_instructions_preserved']
resolve=runpy.run_path(str(root/'scripts/resolve-evidence-history.py'))['resolve']
for name,digest in base['files'].items():resolve(name,digest)
for name,digest in base['link_inputs'].items():assert sha(root/name)==digest
original=root/base['output'];assert sha(original)==base['output_sha256']
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
source=root/'vendor/darling/src/libm/Source/simd_double_constants.c'
fixture=root/'fixtures/hello/simd-double-layout.c'
(folder/'libraries').mkdir(parents=True)
obj=folder/'constants.o';layout_obj=folder/'sdk-layout.o'
commands=[]
for src,out in [(source,obj),(fixture,layout_obj)]:
    command=['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(src),'-o',str(out)]
    subprocess.run(command,check=True);commands.append(command)
name='libDarlingSIMDDouble4Matrix.dylib'
helper=folder/'libraries'/name
command=['ld64.lld-19','-dylib','-arch','x86_64','-platform_version','macos','11','11',
         '-syslibroot',str(sdk),'-lSystem','-no_fixup_chains','-no_adhoc_codesign',
         '-install_name','/usr/lib/'+name,'-exported_symbol','_matrix_identity_double4x4',str(obj),'-o',str(helper)]
subprocess.run(command,check=True);commands.append(command)
data=helper.read_bytes();nm=subprocess.check_output(['llvm-nm-19','--defined-only','--extern-only',str(helper)],text=True)
lines=[line.split() for line in nm.splitlines() if line.strip()]
assert len(lines)==1 and lines[0][-1]=='_matrix_identity_double4x4'
symbol=int(lines[0][0],16);at=32;actual=None
for _ in range(struct.unpack_from('<I',data,16)[0]):
    kind,size=struct.unpack_from('<II',data,at)
    if kind==0x19:
        vm,length,off,filesz=struct.unpack_from('<QQQQ',data,at+24)
        if vm<=symbol and symbol+128<=vm+filesz:actual=data[off+symbol-vm:off+symbol-vm+128]
    at+=size
assert symbol%16==0 and actual is not None
cache=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
provider='/usr/lib/system/libsystem_m.dylib'
address=cache['resolve'](provider,'_matrix_identity_double4x4');assert address
expected=cache['read'](address,128)
assert actual==expected
assert struct.unpack('<16d',actual)==tuple(float(i//4==i%4) for i in range(16))
old=original.read_bytes()
payload,changes=runpy.run_path(str(root/'scripts/macho-named-reexport.py'))['add'](
    old,'/usr/lib/'+name,['_matrix_identity_double4x4'])
assert changes['original_instructions_and_other_bytes_preserved']
library=folder/'libraries/libSystem.B.dylib';library.write_bytes(payload)
inputs=[Path(__file__),source,fixture,helper,library,root/base_path,
        root/args.configuration,root/'scripts/macho-named-reexport.py',
        sdk/'usr/include/simd/types.h',sdk/'usr/include/simd/vector_types.h',
        sdk/'usr/include/simd/matrix.h']
report={**base,'parent_source_build':base_path,'parent_source_build_sha256':sha(root/base_path),
        'parent_link_command':base['command'],'command':[sys.executable,*sys.argv],
        'output':str(library.relative_to(root)),'output_sha256':sha(library),
        'files':{**base['files'],**{str(p.relative_to(root)):sha(p) for p in inputs}},
        'link_inputs':{**base['link_inputs'],str(helper.relative_to(root)):sha(helper)},
        'named_reexports_preserved':base['named_reexports_preserved'],
        'added_named_reexports':changes,
        'constant_helper':str(helper.relative_to(root)),
        'constant_helper_sha256':sha(helper),'constant_build_commands':commands,
        'SDK_layout_compile_assertions_passed':True,'constant_bytes_equal_original':True,
        'constant_bytes':128,'constant_alignment':16,
        'original_constant_sha256':hashlib.sha256(expected).hexdigest(),
        'original_provider':provider,'original_provider_sha256':sha(root/('runtime/fullsystem-libraries'+provider)),
        'original_constant_address':hex(address),'runtime_execution_verified':False,
        'full_Unity_build_verified':False}
(folder/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print('BUILD_REPORT',folder/'build.json')
