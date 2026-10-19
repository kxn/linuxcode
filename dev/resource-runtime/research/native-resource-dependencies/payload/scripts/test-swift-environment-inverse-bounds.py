#!/usr/bin/env python3
"""Check actual CoreVideo inverse metadata and reject corrupted original records."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import runpy
import struct

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler-proof',required=True)
parser.add_argument('--report',required=True)
args=parser.parse_args()
output=root/args.report
assert not output.exists()
proof=json.loads((root/args.compiler_proof).read_text())
assert proof['verified'] and proof['declared_requirements']==1 and proof['emitted_requirements']==2 and proof['native_KeyPath_projections']==6
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for p,h in proof['files'].items():assert sha(root/p)==h,p
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())['corevideo-resource-native']
original=root/('runtime/fullsystem-libraries'+pin['path']);original_sha=sha(original);assert original_sha==pin['sha256']
m=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h','REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
image=m['image'](pin['path']);sections=[(segment,name,address,size) for name,segment,address,size,_ in image.sections]
data=original.read_bytes();cursor=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    command,length=struct.unpack_from('<II',data,cursor)
    if command==2:off,count,stroff,_=struct.unpack_from('<4I',data,cursor+8)
    cursor+=length
symbols=[];environments=[]
for index in range(count):
    start,kind,_,_,address=struct.unpack_from('<IBBHQ',data,off+16*index)
    name=data[stroff+start:data.index(0,stroff+start)].decode()
    if kind&14==14 and name.startswith(('_generic environment ','_symbolic ')):
        symbols.append({'name':name,'address':hex(address)})
        if name.startswith('_generic environment '):environments.append(address)
validate=runpy.run_path(str(root/'scripts/swift-environment-inverse-bounds.py'))['validate']
records=pin['swift_environment_inverse_bounds'];start,end=int(records[0]['start'],16),int(records[0]['end'],16)
def check(mutations=None, rehash=False, change=None, symbol_change=None):
    mutations=mutations or {}
    def read(address,length):
        result=bytearray(m['read'](address,length))
        for at,payload in mutations.items():
            for p in range(max(address,at),min(address+length,at+len(payload))):result[p-address]=payload[p-at]
        return bytes(result)
    selected=copy.deepcopy(records);labels=copy.deepcopy(symbols)
    if change:change(selected[0])
    if symbol_change:symbol_change(labels)
    if rehash:selected[0]['sha256']=hashlib.sha256(read(start,end-start)).hexdigest()
    return validate(read,sections,environments,labels,selected)
assert check()=={start:end}
parameter=start+12+struct.unpack('<i',m['read'](start+12,4))[0]
cases=[
 ('changed_bytes',{start+20:struct.pack('<I',6)},False,None,None,'bytes changed'),
 ('changed_count',{start:struct.pack('<I',8193)},True,None,None,'generic header'),
 ('changed_parameter_count',{start+4:struct.pack('<H',2)},True,None,None,'generic header'),
 ('reserved_parameter_bits',{start+6:bytes([192])},True,None,None,'generic header'),
 ('nonzero_padding',{start+7:b'\x01'},True,None,None,'generic header'),
 ('wrong_protocol_flags',{start+8:struct.pack('<I',0)},True,None,None,'protocol requirement'),
 ('wrong_protocol_reference',{start+16:struct.pack('<i',4)},True,None,None,'protocol reference'),
 ('wrong_inverse_kind',{start+20:struct.pack('<I',4)},True,None,None,'inverse descriptor'),
 ('inverse_parameter_index',{start+28:struct.pack('<H',1)},True,None,None,'inverse descriptor'),
 ('unsupported_inverse_mask',{start+30:struct.pack('<H',2)},True,None,None,'inverse descriptor'),
 ('different_inverse_parameter',{start+24:struct.pack('<i',-8)},True,None,None,'parameter reference'),
 ('changed_parameter_type',{parameter:b'y\0'},False,None,None,'parameter reference'),
 ('unrelated_end_label',{},False,lambda p:p.update(next_symbol='_symbolic missing'),None,'labels or extent'),
 ('extent_overrun',{},False,lambda p:p.update(end=hex(end+4)),None,'labels or extent'),
 ('interior_type_label',{},False,None,lambda rows:rows.append({'name':'_symbolic unexpected','address':hex(start+20)}),'crosses a symbolic type label')]
rejected=[]
for name,mutation,rehash,change,label_change,message in cases:
    try:check(mutation,rehash,change,label_change)
    except ValueError as error:
        assert message in str(error),(name,str(error));rejected.append(name)
    else:raise AssertionError('Invalid inverse metadata accepted: '+name)
assert check()=={start:end} and sha(original)==original_sha
record=dict(verified=True,compiler_proof=args.compiler_proof,compiler_proof_sha256=sha(root/args.compiler_proof),
            original_image_sha256=original_sha,original_header_preserved=True,actual_declared_requirements=1,
            actual_emitted_requirements=2,damaged_actual_records_rejected=rejected,
            original_bytes_preserved_after_tests=True,parser_sha256=sha(root/'scripts/swift-environment-inverse-bounds.py'),
            test_driver_sha256=sha(__file__),full_CoreVideo_API_verified=False)
output.write_text(json.dumps(record,indent=2)+'\n');print('Actual original environment and',len(rejected),'negative cases passed')
