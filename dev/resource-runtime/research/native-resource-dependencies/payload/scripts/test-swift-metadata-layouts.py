#!/usr/bin/env python3
"""Check actual Foundation metadata layouts and reject damaged real records.

This is a read-only structural test, not Swift runtime or Foundation API proof.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import runpy
import struct

project=Path(__file__).resolve().parent.parent
pin=json.loads((project/'config/cache-image-pins.json').read_text())['foundation-native']
source=project/'runtime/fullsystem-libraries'/pin['path'].lstrip('/')
data=source.read_bytes()
assert hashlib.sha256(data).hexdigest()==pin['sha256']
ns=runpy.run_path(str(project/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':project/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':project/'runtime/fullsystem-libraries'})
segments=[];cursor=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    cmd,size=struct.unpack_from('<II',data,cursor)
    if cmd==0x19:
        raw=data[cursor:cursor+size]
        name=raw[8:24].split(b'\0')[0].decode()
        base,length=struct.unpack_from('<QQ',raw,24)
        if name!='__LINKEDIT':
            segments.append({'base':base,'length':length,
                'sections':[raw[72+80*i:152+80*i] for i in range(struct.unpack_from('<I',raw,64)[0])]})
    if cmd==2:symoff,count,stroff,_=struct.unpack_from('<4I',data,cursor+8)
    cursor+=size
environments=[]
for i in range(count):
    off,kind,_,_,value=struct.unpack_from('<IBBHQ',data,symoff+16*i)
    name=data[stroff+off:data.index(0,stroff+off)].decode()
    if kind&0xe==0xe and name.startswith('_generic environment '):environments.append(value)
ns['swift_generic_environments']=environments
original_read=ns['read']
restore=runpy.run_path(str(project/'scripts/restore-swift-metadata.py'))['restore']
def unexpected(*args):raise AssertionError('This original Foundation requires no external recovery cells or writes')
def own(address):return any(s['base']<=address<s['base']+s['length'] for s in segments)
def check(mutations=None):
    mutations=mutations or {}
    def read(address,length):
        result=bytearray(original_read(address,length))
        for start,payload in mutations.items():
            for at in range(max(address,start),min(address+length,start+len(payload))):
                result[at-address]=payload[at-start]
        return bytes(result)
    local=dict(ns,read=read)
    return restore(segments,local,unexpected,unexpected,unexpected,own)
baseline=check()
assert len(baseline['generic_pack_shapes'])==4
assert len(baseline['conditional_pack_shapes'])==8
assert len(baseline['generic_environments'])==5
assert baseline['patches']==[] and baseline['recovery_cells']==0
header=int(baseline['generic_pack_shapes'][0]['header'],16)
params,requirements,_,_=struct.unpack('<4H',original_read(header,8))
pack_header=((header+8+params+3)&~3)+12*requirements
conditional=int(baseline['conditional_pack_shapes'][0]['conformance'],16)
flags=struct.unpack('<I',original_read(conditional+12,4))[0]
conditional_start=conditional+16+(4 if flags&64 else 0)+12*((flags>>8)&255)
environment=int(baseline['generic_environments'][0]['start'],16)
cases={
 'unknown_generic_context_extension':({header+6:struct.pack('<H',2)},'Unsupported Swift generic-context extensions'),
 'pack_count_mismatch':({pack_header:bytes(2)},'Invalid Swift generic pack shape header'),
 'reserved_pack_shape_bits':({pack_header+4+6:struct.pack('<H',1)},'Invalid Swift generic pack shape descriptor'),
 'reserved_conditional_pack_shape_bits':({conditional_start+6:struct.pack('<H',1)},'Invalid Swift conditional pack shape descriptor'),
 'zero_environment_levels':({environment:struct.pack('<I',0)},'Invalid Swift generic environment flags'),
}
rejected=[]
for name,(mutations,message) in cases.items():
    try:check(mutations)
    except ValueError as error:
        assert message in str(error),(name,str(error))
        rejected.append(name)
    else:raise AssertionError('Damaged actual metadata was accepted: '+name)
assert check()==baseline
report={'checked_at':datetime.now(timezone.utc).isoformat(),
    'source_sha256':pin['sha256'],'source_modified':False,
    'generic_pack_contexts':4,'conditional_pack_conformances':8,
    'binary_generic_environments':5,'damaged_real_records_rejected':rejected,
    'baseline_unchanged_after_negative_tests':True,
    'execution_verified':False,'full_compatibility':False,
    'scope':'Actual pinned Foundation structural metadata recovery and damaged-record rejection only; no runtime metadata access or Foundation API execution claim.'}
(project/'artifacts/swift-metadata-layouts.json').write_text(json.dumps(report,indent=2)+'\n')
print('Actual Foundation pack/environment layouts and five damaged-record rejection checks passed')
