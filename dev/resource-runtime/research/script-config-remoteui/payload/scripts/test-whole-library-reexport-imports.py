#!/usr/bin/env python3
"""Check scoped namespaces against original imports and mutated Mach-O declarations."""
from pathlib import Path
import argparse,copy,hashlib,json,runpy,struct,tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True)
args=parser.parse_args()
out=root/args.output;assert not out.exists()
read=lambda p:json.loads((root/p).read_text())
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
discover=runpy.run_path(str(root/'scripts/exact-reexport-imports.py'))['discover']
provider='/System/Library/Frameworks/SwiftUI.framework/Versions/A/SwiftUI'
core='/System/Library/Frameworks/SwiftUICore.framework/Versions/A/SwiftUICore'
pins=read('config/coregraphics-image-pins.json')
audit=read('artifacts/authkitui-original-scoped-reexport-import-audit-v1.json')
image=pins[audit['target']]['path'];deps=ns['image'](image).dependencies
wanted={int(row['target'],16) for row in audit['rows']}
exact,proof=discover(ns['image'],deps,wanted,root/'runtime/fullsystem-libraries',whole_library_providers=[provider])
assert proof==audit['explicit_reexports']
assert all(exact[int(row['target'],16)]==row['exports'] and row['selected'] for row in audit['rows'])
legacy=read('artifacts/quicklook-closure-soundanalysis-original-reexport-import-audit-v1.json')
oldimage=pins[legacy['target']]['path']
oldwanted={int(row['target'],16) for row in legacy['rows']}
oldexact,oldproof=discover(ns['image'],ns['image'](oldimage).dependencies,oldwanted,root/'runtime/fullsystem-libraries')
assert oldproof==legacy['explicit_reexports']
assert all(oldexact[int(row['target'],16)]==row['exports'] for row in legacy['rows'])
folder=Path(tempfile.mkdtemp(prefix='whole-reexport-controls-',dir=root/'runtime'))

def declarations(data):
    at=32;deps=[];reexports=[];commands=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,at)
        if command in (0xc,0x80000018,0x8000001f,0x80000023):
            start=at+struct.unpack_from('<I',data,at+8)[0]
            name=data[start:data.index(0,start)].decode();deps.append(name)
            commands.append((command,at,size,start,name))
            if command==0x8000001f:reexports.append(name)
        at+=size
    return deps,reexports,commands

# Remove the actual namespace declaration, while retaining every original
# export address and changing only LC_REEXPORT_DYLIB to LC_LOAD_DYLIB.
data=bytearray((root/'runtime/fullsystem-libraries'/provider.lstrip('/')).read_bytes())
row=next(row for row in declarations(data)[2] if row[0]==0x8000001f and row[4]==core)
struct.pack_into('<I',data,row[1],0xc)
path=folder/'swiftui-regular-load.dylib';path.write_bytes(data)
node=copy.copy(ns['image'](provider));node.dependencies,node.reexports,_=declarations(data)
changed=lambda path:node if path==provider else ns['image'](path)
missing,_=discover(changed,deps,wanted,root/'runtime/fullsystem-libraries',whole_library_providers=[provider])
lost=[row['target'] for row in audit['rows'] if not missing[int(row['target'],16)]]
assert len(lost)==25
try:discover(ns['image'],deps,wanted,root/'runtime/fullsystem-libraries',whole_library_providers=[core])
except AssertionError:unlisted=True
else:raise AssertionError('Accepted a provider outside the original dependency list')

# Redirect one original Core reexport declaration back to SwiftUI, creating
# an actual declaration cycle without touching the reference cache.
data=bytearray((root/'runtime/fullsystem-libraries'/core.lstrip('/')).read_bytes())
row=next(row for row in declarations(data)[2] if row[0]==0x8000001f)
payload=provider.encode()+b'\0';assert len(payload)<=row[1]+row[2]-row[3]
data[row[3]:row[1]+row[2]]=payload.ljust(row[1]+row[2]-row[3],b'\0')
cycle_path=folder/'swiftuicore-reexport-cycle.dylib';cycle_path.write_bytes(data)
cycle=copy.copy(ns['image'](core));cycle.dependencies,cycle.reexports,_=declarations(data)
changed=lambda path:cycle if path==core else ns['image'](path)
try:discover(changed,deps,wanted,root/'runtime/fullsystem-libraries',whole_library_providers=[provider])
except ValueError as error:assert 'Cyclic' in str(error)
else:raise AssertionError('Accepted a cyclic reexport namespace')
report=dict(verified=True,actual_original_import_rows=len(audit['rows']),recovered_whole_library_imports=25,
    legacy_explicit_only_import_rows=len(legacy['rows']),legacy_proof_exactly_unchanged=True,
    actual_declaration_mutations=2,removed_reexport_leaves_25_unresolved=True,
    undeclared_top_provider_rejected=True,cyclic_namespace_rejected=True,
    private_mutation_files={str(p.relative_to(root)):sha(p.relative_to(root)) for p in [path,cycle_path]},
    source_sha256={p:sha(p) for p in ['scripts/exact-reexport-imports.py',str(Path(__file__).relative_to(root)),
        'artifacts/authkitui-original-scoped-reexport-import-audit-v1.json',
        'artifacts/quicklook-closure-soundanalysis-original-reexport-import-audit-v1.json']})
out.write_text(json.dumps(report,indent=2)+'\n')
print('VERIFIED original rows',len(audit['rows']),'recovered',25,'legacy rows',len(legacy['rows']))
