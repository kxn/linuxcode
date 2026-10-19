#!/usr/bin/env python3
"""Validate actual IDSFoundation records and reject damaged ABI fields/sections."""
from pathlib import Path
import argparse
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
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
proof=json.loads((root/args.compiler_proof).read_text())
assert proof['verified'] and proof['native_local_distributed_calls']==2
assert proof['emitted_accessible_function_records'] and not proof['original_metadata_edited']
for path,expected in proof['files'].items():assert sha(root/path)==expected,path
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())['idsfoundation-resource-native']
original=root/('runtime/fullsystem-libraries'+pin['path']);before=sha(original)
assert before==pin['sha256']
m=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
sections=[(segment,name,address,length) for name,segment,address,length,_ in m['image'](pin['path']).sections]
validate=runpy.run_path(str(root/'scripts/swift-accessible-function-records.py'))['validate']
records=validate(m['read'],sections)
assert len(records)==19
environments={int(row['environment'],16) for row in records if row['environment']}
assert len(environments)==4 and 0x7ff818e40750 in environments
assert all(row['flags']==1 and row['async_context_size'] is not None for row in records)
table=next(row for row in sections if row[1]=='__swift5_acfuncs')
at=int(records[0]['record'],16);fn=int(records[0]['function'],16)
name=at+struct.unpack('<i',m['read'](at,4))[0]
type_ref=int(records[0]['function_type'],16)
pack=lambda value:struct.pack('<i',value)
def check(mutations=None,section_change=None):
    rows=list(sections)
    if section_change:rows[rows.index(table)]=section_change(table)
    def read(address,length):
        data=bytearray(m['read'](address,length))
        for start,payload in (mutations or {}).items():
            for cursor in range(max(start,address),min(start+len(payload),address+length)):
                data[cursor-address]=payload[cursor-start]
        return bytes(data)
    return validate(read,rows)
cases=[
    ('unaligned_table',{},lambda s:(s[0],s[1],s[2]+1,s[3]),'table extent'),
    ('truncated_table',{},lambda s:(s[0],s[1],s[2],s[3]-1),'table extent'),
    ('unknown_flags',{at+16:pack(2)},None,'flags'),
    ('null_name',{at:pack(0)},None,'Null required'),
    ('null_type',{at+8:pack(0)},None,'Null required'),
    ('null_function',{at+12:pack(0)},None,'Null required'),
    ('name_outside_strings',{at:pack(table[2]+4-at)},None,'name outside'),
    ('unterminated_name',{name:b'A'*4096},None,'Unbounded'),
    ('invalid_UTF8_name',{name:b'\xff'},None,'utf-8'),
    ('environment_outside_typeref',{at+4:pack(table[2]-(at+4))},None,'environment outside'),
    ('unaligned_environment',{at+4:pack(0x7ff818e40751-(at+4))},None,'environment outside'),
    ('type_outside_typeref',{at+8:pack(table[2]-(at+8))},None,'type outside'),
    ('empty_type',{type_ref:b'\0'},None,'type outside'),
    ('function_outside_code',{at+12:pack(table[2]-(at+12))},None,'entry outside'),
    ('invalid_async_code',{fn:pack(4)},None,'async code outside'),
    ('short_async_context',{fn+4:pack(8)},None,'context size'),
    ('unaligned_async_context',{fn+4:pack(17)},None,'context size'),
    ('oversized_async_context',{fn+4:pack((1<<24)+8)},None,'context size')]
rejected=[]
for name,mutation,change,message in cases:
    try:check(mutation,change)
    except ValueError as error:
        assert message in str(error),(name,str(error));rejected.append(name)
    else:raise AssertionError('Damaged accessible metadata accepted: '+name)
assert check()==records and sha(original)==before
record=dict(verified=True,original_image_sha256=before,actual_records=len(records),actual_environments=len(environments),
    unlabelled_environment_recovered_from_typed_table=True,original_bytes_preserved=True,
    damaged_actual_records_rejected=rejected,records=records,compiler_proof=args.compiler_proof,
    compiler_proof_sha256=sha(root/args.compiler_proof),helper_sha256=sha(root/'scripts/swift-accessible-function-records.py'),
    driver_sha256=sha(Path(__file__)),full_IDSFoundation_API_verified=False)
output.write_text(json.dumps(record,indent=2)+'\n')
print('Validated',len(records),'actual records and',len(environments),'environments;',len(rejected),'negative cases rejected')
