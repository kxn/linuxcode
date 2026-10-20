#!/usr/bin/env python3
"""Check original HealthKit marker metadata and reject changed records/labels."""
from pathlib import Path
import argparse,copy,hashlib,json,runpy,struct
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--compiler-proof',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
output=root/args.output;assert not output.exists()
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
proof=json.loads((root/args.compiler_proof).read_text());assert proof['verified'] and proof['declared_requirements']==4 and proof['emitted_requirements']==3 and proof['native_KeyPath_projections']==12
for name,digest in proof['files'].items():assert sha(name)==digest,name
image='/System/Library/Frameworks/HealthKit.framework/Versions/A/HealthKit';original='runtime/fullsystem-libraries'+image
data=(root/original).read_bytes();cursor=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    command,size=struct.unpack_from('<II',data,cursor)
    if command==2:off,count,stroff,_=struct.unpack_from('<4I',data,cursor+8)
    cursor+=size
symbols=[]
for i in range(count):
    start,kind,_,_,address=struct.unpack_from('<IBBHQ',data,off+16*i)
    name=data[stroff+start:data.index(0,stroff+start)].decode()
    if kind&14==14 and name.startswith(('_generic environment ','_symbolic ')):symbols.append(dict(name=name,address=hex(address)))
ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h','REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
sections=[(seg,n,a,z) for n,seg,a,z,_ in ns['image'](image).sections];environments=[int(row['address'],16) for row in symbols if row['name'].startswith('_generic environment ')]
records=json.loads((root/'config/healthkit-codable-marker-environment-bounds-v1.json').read_text());assert len(records)==1
start,end=int(records[0]['start'],16),int(records[0]['end'],16)
validate=runpy.run_path(str(root/'scripts/swift-environment-marker-bounds.py'))['validate']
def check(mutations=None,change=None,labels=None,rehash=False,wrong_resolver=False):
    mutations=mutations or {};selected=copy.deepcopy(records);selected_symbols=copy.deepcopy(symbols)
    def read(a,n):
        b=bytearray(ns['read'](a,n))
        for address,payload in mutations.items():
            for k in range(max(a,address),min(a+n,address+len(payload))):b[k-a]=payload[k-address]
        return bytes(b)
    if rehash:selected[0]['sha256']=hashlib.sha256(read(start,end-start)).hexdigest()
    if change:change(selected[0])
    if labels:labels(selected_symbols)
    selected_ns={**ns,'read':read}
    if wrong_resolver:selected_ns['resolve']=lambda path,name:ns['resolve'](path,name)+8
    return validate(selected_ns,sections,environments,selected_symbols,selected)
assert check()=={start:end}
cases=[('stale_hash',{start+7:b'\x01'},None,None,False,False),
 ('wrong_count',{start:struct.pack('<I',12289)},None,None,True,False),
 ('wrong_parameter_count',{start+4:struct.pack('<H',2)},None,None,True,False),
 ('reserved_parameter_flags',{start+6:b'\xc0'},None,None,True,False),
 ('nonzero_padding',{start+7:b'\x01'},None,None,True,False),
 ('wrong_requirement_kind',{start+8:struct.pack('<I',1)},None,None,True,False),
 ('wrong_parameter_reference',{start+12:struct.pack('<i',4)},None,None,True,False),
 ('wrong_protocol_identity',{},None,None,False,True),
 ('objc_protocol_flag',{start+16:struct.pack('<i',struct.unpack('<i',ns['read'](start+16,4))[0]|2)},None,None,True,False),
 ('wrong_extent',{},lambda r:r.update(end=hex(end+4)),None,False,False),
 ('wrong_next_label',{},lambda r:r.update(next_symbol='_symbolic missing'),None,False,False),
 ('interior_type_label',{},None,lambda rows:rows.append(dict(name='_symbolic injected',address=hex(start+20))),False,False)]
rejected=[]
for name,mutations,change,labels,rehash,wrong in cases:
    try:check(mutations,change,labels,rehash,wrong)
    except ValueError:rejected.append(name)
    else:raise AssertionError('Accepted changed marker metadata: '+name)
assert check()=={start:end} and (root/original).read_bytes()==data
report=dict(verified=True,compiler_proof=args.compiler_proof,compiler_proof_sha256=sha(args.compiler_proof),
 original_image=image,original_image_sha256=sha(original),declared_requirements=4,emitted_requirements=3,
 original_header_preserved=True,in_memory_original_record_controls=True,rejected_controls=rejected,
 source_sha256={n:sha(n) for n in ['scripts/swift-environment-marker-bounds.py','scripts/test-swift-environment-marker-bounds.py','config/healthkit-codable-marker-environment-bounds-v1.json']},
 full_HealthKit_API_verified=False,resource_compilation_verified=False)
output.write_text(json.dumps(report,indent=2)+'\n');print('VERIFIED original HealthKit environment and',len(rejected),'rejecting controls')
