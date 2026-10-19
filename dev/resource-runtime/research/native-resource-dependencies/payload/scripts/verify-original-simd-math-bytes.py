#!/usr/bin/env python3
"""Compare selected native math instruction ranges and read-only data to the cache."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report',required=True)
args=parser.parse_args()
output=root/args.report
assert not output.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())['simd-math-resource-native']
original=root/('runtime/fullsystem-libraries'+pin['path'])
assert sha(original)==pin['sha256']
m=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
image=m['image'](pin['path'])
source=original.read_bytes()
rebuilt=root/'runtime/rebuilt-simd-math-resource-native/libsystem_m.dylib'
data=rebuilt.read_bytes()
reconstruction=json.loads((rebuilt.parent/'reconstruction.json').read_text())
assert sha(rebuilt)==reconstruction['staged_image_sha256']
def commands(data):
    at=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,length=struct.unpack_from('<II',data,at)
        yield command,at
        at+=length
for command,at in commands(source):
    if command==0x19 and source[at+8:at+24].split(b'\0')[0]==b'__TEXT':
        original_base=struct.unpack_from('<Q',source,at+24)[0]
    if command==0x26:
        offset,length=struct.unpack_from('<II',source,at+8)
        starts_data=source[offset:offset+length]
starts=[];value=original_base;at=0
while at<len(starts_data):
    delta=shift=0
    while True:
        byte=starts_data[at];at+=1;delta|=(byte&127)<<shift
        if not byte&128:break
        shift+=7;assert shift<64
    if delta==0:break
    value+=delta;starts.append(value)
assert len(starts)==reconstruction['code_analysis']['function_entries']
segments=[]
for command,at in commands(data):
    if command==0x19:
        vm,size,offset,length=struct.unpack_from('<QQQQ',data,at+24)
        segments.append((vm,offset,length))
def rebuilt_bytes(original_address,length):
    address=original_address-original_base
    for vm,offset,size in segments:
        if vm<=address and address+length<=vm+size:
            return data[offset+address-vm:offset+address-vm+length]
    raise ValueError('Unmapped rebuilt range')
names=['___invert_f3','__simd_exp2_f4','__simd_exp_f4','__simd_log2_f4',
       '__simd_log_f4','__simd_pow_f4','__simd_sin_f4']
functions=[]
for name in names:
    start=m['resolve'](pin['path'],name);assert start in starts
    end=starts[starts.index(start)+1]
    before=m['read'](start,end-start);after=rebuilt_bytes(start,end-start)
    assert before==after,name
    functions.append(dict(name=name,start=hex(start),length=end-start,sha256=hashlib.sha256(before).hexdigest(),identical=True))
sections=[]
for name,segment,address,length,_ in image.sections:
    if segment!='__TEXT' or name in ('__text','__stubs','__stub_helper') or not length:continue
    before=m['read'](address,length);after=rebuilt_bytes(address,length)
    assert before==after,name
    sections.append(dict(name=name,length=length,sha256=hashlib.sha256(before).hexdigest(),identical=True))
assert sections
record=dict(verified=True,original_image_sha256=sha(original),rebuilt_image_sha256=sha(rebuilt),
    original_function_instruction_ranges=functions,original_readonly_sections=sections,
    full_original_function_boundaries_used=True,original_routines_and_constants_byte_identical=True,
    scalar_IEEE_equivalence_verified=False,full_math_library_correctness_verified=False,
    driver_sha256=sha(Path(__file__)))
output.write_text(json.dumps(record,indent=2)+'\n')
print('All seven function ranges and',len(sections),'read-only sections are byte-identical')
