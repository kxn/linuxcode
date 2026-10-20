#!/usr/bin/env python3
"""Check a real singleton class and reject damaged decoded reference fixtures.

The mutations are overlays on cache reads/decoded pointers in memory. No
damaged image is emitted or executed; this is an ABI structural test.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',required=True)
parser.add_argument('--symbolic-reference',required=True,type=lambda s:int(s,0))
parser.add_argument('--output',required=True)
args=parser.parse_args();output=root/args.output;assert not output.exists()
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
original=root/('runtime/fullsystem-libraries'+pin['path']);assert sha(original)==pin['sha256']
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
image=ns['image'](pin['path']);sections=[(g,n,a,z) for n,g,a,z,f in image.sections]
start=args.symbolic_reference;assert ns['read'](start,1)==b'\x01'
descriptor=start+1+struct.unpack('<i',ns['read'](start+1,4))[0]
metadata=descriptor+48+struct.unpack('<i',ns['read'](descriptor+48,4))[0]
helper='scripts/swift-singleton-objc-metadata.py';validate=runpy.run_path(str(root/helper))['validate']
baseline=validate(ns['read'],ns['pointer'],sections,descriptor,metadata)
ro=int(baseline['class_ro'],16);meta=int(baseline['metaclass'],16);meta_ro=int(baseline['metaclass_ro'],16)
flags=struct.unpack('<I',ns['read'](descriptor,4))[0]
cases=[('resilient_union_variant',{descriptor:struct.pack('<I',flags|0x20000000)},{}),
       ('generic_class_variant',{descriptor:struct.pack('<I',flags|128)},{}),
       ('wrong_descriptor_identity',{}, {metadata+64:descriptor+4}),
       ('non_swift_class_data',{}, {metadata+32:ro}),
       ('metaclass_outside_image',{}, {metadata:8}),
       ('class_ro_with_meta_flag',{ro:struct.pack('<I',struct.unpack('<I',ns['read'](ro,4))[0]|1)},{}),
       ('metaclass_ro_without_meta_flag',{meta_ro:struct.pack('<I',struct.unpack('<I',ns['read'](meta_ro,4))[0]&~1)},{}),
       ('different_metaclass_name',{}, {meta_ro+24:ns['pointer'](ro+24)+1})]
rejected=[]
for name,mutations,pointers in cases:
    def read(address,length):
        b=bytearray(ns['read'](address,length))
        for at,payload in mutations.items():
            for i in range(max(address,at),min(address+length,at+len(payload))):b[i-address]=payload[i-at]
        return bytes(b)
    def pointer(address):return pointers[address] if address in pointers else ns['pointer'](address)
    try:validate(read,pointer,sections,descriptor,metadata)
    except (AssertionError,ValueError,struct.error,UnicodeDecodeError):rejected.append(name)
    else:raise AssertionError('Accepted '+name)
assert validate(ns['read'],ns['pointer'],sections,descriptor,metadata)==baseline
record=dict(verified=True,target=args.target,symbolic_reference=hex(start),original_sha256=sha(original),
            original_contract=baseline,rejected_decoded_reference_fixtures=rejected,
            actual_original_methods_or_protocols_replaced=False,no_images_emitted=True,runtime_behavior_verified=False,
            sources={n:sha(root/n) for n in [str(Path(__file__).relative_to(root)),helper,
                'scripts/dsc-image.py','vendor/swift-abi-reference/include/swift/ABI/Metadata.h']})
output.write_text(json.dumps(record,indent=2)+'\n');print('REAL_SINGLETON_CLASS_AND_DECODED_REFERENCE_CONTROLS_OK',len(rejected))
