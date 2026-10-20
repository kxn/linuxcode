#!/usr/bin/env python3
"""Compare recovered singleton class names, methods, protocols and cache state.

This reads the actual original cache and actual emitted Mach-O. It verifies
metadata identities and damaged candidate rejection, not AppKit API semantics.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct
import subprocess

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args();output=root/args.output;assert not output.exists()
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
folder=root/('runtime/rebuilt-'+args.target);candidate=folder/Path(pin['path']).name
report=json.loads((folder/'reconstruction.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(candidate)==report['staged_image_sha256']
original=root/('runtime/fullsystem-libraries'+pin['path']);assert sha(original)==pin['sha256']
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
image=ns['image'](pin['path']);base=image.base
original_sections=[(g,n,a,z) for n,g,a,z,f in image.sections]
contracts=report['swift_metadata']['singleton_objc_metadata'];assert contracts
validate=runpy.run_path(str(root/'scripts/swift-singleton-objc-metadata.py'))['validate']
parser_module=runpy.run_path(str(root/'scripts/inspect-preserved-patch-got.py'))
symbols=subprocess.check_output(['llvm-nm-19','--defined-only',str(root/'runtime/fullsystem-libraries/usr/lib/libobjc.A.dylib')],text=True)
opt=next(int(l.split()[0],16) for l in symbols.splitlines() if l.split()[-1]=='__objc_opt_data')
selector_base=opt+struct.unpack('<q',ns['read'](opt+40,8))[0]

def cstring(read,address):
    if not address:return b''
    result=bytearray()
    for i in range(0,1048576,32):
        chunk=read(address+i,32);stop=chunk.find(b'\0')
        result.extend(chunk if stop<0 else chunk[:stop])
        if stop>=0:return bytes(result)
    raise AssertionError('Unterminated string')

def base_list(slot,kind):
    value=ns['pointer'](slot)
    if not value&1:return value
    header=value&~1;size,count=struct.unpack('<II',ns['read'](header,8))
    assert size==8 and 1<=count<=4096
    entry=header+8*count;raw=struct.unpack('<Q',ns['read'](entry,8))[0]
    delta=raw>>16
    if delta&(1<<47):delta-=1<<48
    address=entry+delta
    if not any(start<=address<start+length for g,n,start,length in original_sections):
        empty=struct.unpack('<Q' if kind=='protocol' else '<I',ns['read'](address if kind=='protocol' else address+4,8 if kind=='protocol' else 4))[0]
        assert empty==0
        return 0
    return address

mutation_offsets={}
def inspect(data):
    segments,sections,streams=parser_module['macho'](data)
    def offset(address,size):
        return next(off+address-vm for name,vm,length,off,filesize in segments
                    if vm<=address and address+size<=vm+filesize)
    def read(address,size):return data[offset(address,size):offset(address,size)+size]
    def pointer(address):return struct.unpack('<Q',read(address,8))[0]
    bindings=parser_module['binding_stream'](data[streams[2]:streams[2]+streams[3]])
    methods=protocols=objects=0
    for contract in contracts:
        cls=int(contract['metadata'],16);descriptor=int(contract['descriptor'],16)
        assert validate(ns['read'],ns['pointer'],original_sections,descriptor,cls)==contract
        for obj,ro in [(cls,int(contract['class_ro'],16)),
                       (int(contract['metaclass'],16),int(contract['metaclass_ro'],16))]:
            objects+=1
            assert pointer(obj-base+32)==ns['pointer'](obj+32)-base
            assert pointer(obj-base+16)==pointer(obj-base+24)==0
            key=next((i,obj-base+16-vm) for i,(name,vm,length,off,filesize) in enumerate(segments)
                     if vm<=obj-base+16<vm+length)
            assert bindings[key][0]=='__objc_empty_cache'
            assert cstring(read,pointer(ro-base+24))==cstring(ns['read'],ns['pointer'](ro+24))
            mutation_offsets.setdefault('class_data_flags',offset(obj-base+32,8))
            mutation_offsets.setdefault('cache_state',offset(obj-base+24,8))
            old=base_list(ro+32,'method');new=pointer(ro-base+32)
            if not old:assert new==0
            else:
                flags,count=struct.unpack('<II',ns['read'](old,8))
                assert struct.unpack('<II',read(new,8))==(24,count)
                for index in range(count):
                    at=old+8+index*(12 if flags&0x80000000 else 24)
                    if flags&0x80000000:
                        a,b,c=struct.unpack('<iii',ns['read'](at,12))
                        name=selector_base+a if flags&0x40000000 else ns['pointer'](at+a)
                        types=at+4+b if b else 0;imp=at+8+c if c else 0
                    else:name,types,imp=(ns['pointer'](at+x) for x in (0,8,16))
                    dest=new+8+index*24
                    assert cstring(read,pointer(dest))==cstring(ns['read'],name)
                    assert cstring(read,pointer(dest+8))==cstring(ns['read'],types)
                    assert imp and pointer(dest+16)==imp-base
                    mutation_offsets.setdefault('method_implementation',offset(dest+16,8))
                    mutation_offsets.setdefault('method_selector',offset(pointer(dest),1))
                    methods+=1
            old=base_list(ro+40,'protocol');new=pointer(ro-base+40)
            old_count=struct.unpack('<Q',ns['read'](old,8))[0] if old else 0
            new_count=pointer(new) if new else 0
            assert old_count==new_count and old_count<=4096
            for index in range(old_count):
                a=ns['pointer'](old+8+index*8);b=pointer(new+8+index*8)
                assert cstring(ns['read'],ns['pointer'](a+8))==cstring(read,pointer(b+8))
                protocols+=1
    return dict(classes=len(contracts),class_and_metaclass_objects=objects,
                original_method_entries_compared=methods,original_protocol_names_compared=protocols)

data=candidate.read_bytes();positive=inspect(data);negative=[]
for name,at in mutation_offsets.items():
    bad=bytearray(data);bad[at]^=1
    try:inspect(bytes(bad))
    except (AssertionError,ValueError,StopIteration,struct.error):negative.append(name)
    else:raise AssertionError('Accepted '+name)
assert len(negative)==4 and inspect(data)==positive
result=dict(verified=True,target=args.target,positive=positive,rejected_real_candidate_mutations=negative,
            no_binary_copies_written=True,runtime_behavior_verified=False,
            original_sha256=sha(original),candidate_sha256=sha(candidate),
            sources={n:sha(root/n) for n in [str(Path(__file__).relative_to(root)),
                'scripts/swift-singleton-objc-metadata.py','scripts/inspect-preserved-patch-got.py']})
output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(positive), 'NEGATIVE_CONTROLS',len(negative))
