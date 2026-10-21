#!/usr/bin/env python3
"""Check original stub metadata and reject wrong aliases, ordinals and extents."""
from pathlib import Path
import hashlib,json,runpy,struct,tempfile
r=Path(__file__).resolve().parent.parent;folder=Path(tempfile.mkdtemp(prefix='original-stub-import-controls-',dir=r/'runtime'));source=r/'scripts/verify-original-stub-import.py';verify=runpy.run_path(str(source))['verify'];ns=runpy.run_path(str(r/'scripts/dsc-image.py'),init_globals={'REFERENCE_CACHE_PATH':r/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h','REFERENCE_LIBRARY_ROOT':r/'runtime/fullsystem-libraries'});image='/System/Library/PrivateFrameworks/MediaKit.framework/Versions/A/MediaKit';provider='/usr/lib/libSystem.B.dylib';target=0x7ff802e6ba54;slots=['0x7ff8400561b0'];root=r/'runtime/fullsystem-libraries';positive=verify(ns,image,target,slots,'_wait4',provider,root);cases=[]
def reject(name,operation):
 try:operation()
 except AssertionError:cases.append(name)
 else:raise AssertionError('Incorrect binding accepted: '+name)
reject('same_address_different_original_symbol',lambda:verify(ns,image,target,slots,'___wait4_nocancel',provider,root))
reject('wrong_declared_dependency_ordinal',lambda:verify(ns,image,target,slots,'_wait4','/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation',root))
reject('wrong_implementation_address',lambda:verify(ns,image,target+1,slots,'_wait4',provider,root))
reject('unrelated_GOT_slot',lambda:verify(ns,image,target,['0x7ff8400561b8'],'_wait4',provider,root))
owned=folder/'changed-input';p=owned/image.lstrip('/');p.parent.mkdir(parents=True);q=owned/provider.lstrip('/');q.parent.mkdir(parents=True);q.symlink_to(root/provider.lstrip('/'));original=(root/image.lstrip('/')).read_bytes();b=bytearray(original);at=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
 c,length=struct.unpack_from('<II',b,at)
 if c==2:symoff=struct.unpack_from('<I',b,at+8)[0]
 at+=length
index=positive['stubs'][0]['symbol_index'];struct.pack_into('<H',b,symoff+index*16+6,0x400);p.write_bytes(b);reject('changed_original_symbol_ordinal',lambda:verify(ns,image,target,slots,'_wait4',provider,owned))
p.write_bytes(original[:64]);reject('truncated_original_load_commands',lambda:verify(ns,image,target,slots,'_wait4',provider,owned))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report=dict(verified=True,positive_original_stub=positive,negative_cases=cases,negative_count=len(cases),source_files={str(x.relative_to(r)):sha(x) for x in [Path(__file__),source,r/'scripts/dsc-image.py']},no_image_emitted=True,full_goal_complete=False);(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print('EVIDENCE',folder/'result.json')
