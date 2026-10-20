#!/usr/bin/env python3
"""Corrupt real symbol/index tables in memory; never write binary copies."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--original',required=True)
parser.add_argument('--candidate',required=True)
parser.add_argument('--well-formed-control',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
output=root/args.output
assert not output.exists()
module=runpy.run_path(str(root/'scripts/verify-dysymtab-alias-repair.py'))
verify=module['verify']
original=(root/args.original).read_bytes()
candidate=(root/args.candidate).read_bytes()
positive=verify(original,candidate)


def locations(data):
    result={}
    at=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,at)
        if cmd in (2,0xb):result[cmd]=at
        at+=size
    return result


loc=locations(candidate)
symoff,count,stroff,strsize=struct.unpack_from('<4I',candidate,loc[2]+8)
indirectoff,indirectcount=struct.unpack_from('<II',candidate,loc[0xb]+56)
oldloc=locations(original)
oldindirect,oldcount=struct.unpack_from('<II',original,oldloc[0xb]+56)
assert oldcount==indirectcount
records=[struct.unpack_from('<IBBHQ',candidate,symoff+16*i) for i in range(count)]
mutations=[]
bad=bytearray(candidate);struct.pack_into('<I',bad,loc[0xb]+20,struct.unpack_from('<I',original,oldloc[0xb]+20)[0]);mutations.append(('stale_defined_count',bad))
alias=next(i for i,r in enumerate(records) if r[1]==0xb)
bad=bytearray(candidate);struct.pack_into('<Q',bad,symoff+16*alias+8,records[alias][4]+1);mutations.append(('changed_alias_target',bad))
undefined=next(i for i,r in enumerate(records) if r[1]==1)
bad=bytearray(candidate);struct.pack_into('<H',bad,symoff+16*undefined+6,records[undefined][3]^0x40);mutations.append(('changed_undefined_weak_flag',bad))
defined=next(i for i,r in enumerate(records) if r[1]&0xe==0xe)
bad=bytearray(candidate);struct.pack_into('<Q',bad,symoff+16*defined+8,records[defined][4]^1);mutations.append(('changed_defined_address',bad))
bad=bytearray(candidate);bad[stroff+records[alias][0]]^=1;mutations.append(('changed_symbol_string',bad))
special=next(i for i in range(indirectcount) if struct.unpack_from('<I',candidate,indirectoff+4*i)[0]&0xc0000000)
bad=bytearray(candidate);value=struct.unpack_from('<I',bad,indirectoff+4*special)[0];struct.pack_into('<I',bad,indirectoff+4*special,value^0x40000000);mutations.append(('changed_special_indirect_marker',bad))
bad=bytearray(candidate);struct.pack_into('<I',bad,loc[2]+12,count-1);mutations.append(('omitted_symbol_record',bad))
cases=[]
for label,broken in mutations:
    try:
        verify(original,bytes(broken))
    except (AssertionError,ValueError,struct.error,UnicodeDecodeError):
        cases.append(dict(case=label,rejected=True))
    else:
        raise AssertionError('Accepted '+label)
# This real cache image has no affected indirect indices. Seed an undefined
# reference in in-memory copies to exercise remapping without claiming that
# this reference appeared in the original image or executing either copy.
old_undefined=next(i for i,r in enumerate(module['tables'](original)['records']) if r[1]==1)
seeded_original=bytearray(original)
struct.pack_into('<I',seeded_original,oldindirect,old_undefined)
seeded_candidate=bytearray(candidate)
struct.pack_into('<I',seeded_candidate,indirectoff,undefined)
seeded_positive=verify(bytes(seeded_original),bytes(seeded_candidate))
assert seeded_positive['remapped_indirect_entries']>0
struct.pack_into('<I',seeded_candidate,indirectoff,old_undefined)
try:
    verify(bytes(seeded_original),bytes(seeded_candidate))
except AssertionError:
    seeded_bad_index_rejected=True
else:
    raise AssertionError('Accepted stale index in seeded fixture')
control=(root/args.well_formed_control).read_bytes()
control_loc=locations(control)
off,n,strings,size=struct.unpack_from('<4I',control,control_loc[2]+8)
ioff,icount=struct.unpack_from('<II',control,control_loc[0xb]+56)
inputs=(control[off:off+16*n],control[strings:strings+size],control[control_loc[0xb]:control_loc[0xb]+80],control[ioff:ioff+4*icount])
result=runpy.run_path(str(root/'scripts/normalize-dysymtab-aliases.py'))['normalize'](*inputs)
assert tuple(map(bytes,result[:3]))==(inputs[0],inputs[2],inputs[3]) and not result[3]['repaired']
sha=lambda p:hashlib.sha256((root/p).read_bytes()).hexdigest()
record=dict(verified=True,positive=positive,corruption_controls=cases,
    seeded_undefined_reference_fixture=dict(positive=seeded_positive,
        stale_index_rejected=seeded_bad_index_rejected,original_image_reference=False),
    well_formed_real_image_byte_preserving=True,no_binary_copies_written=True,runtime_behavior_verified=False,
    inputs={p:sha(p) for p in [args.original,args.candidate,args.well_formed_control]},
    sources={p:sha(p) for p in [str(Path(__file__).relative_to(root)),
        'scripts/normalize-dysymtab-aliases.py','scripts/verify-dysymtab-alias-repair.py']})
output.write_text(json.dumps(record,indent=2)+'\n')
print('ACTUAL_NLIST_ALIAS_PARTITION_INDIRECT_IDENTITY_AND_CORRUPTION_CONTROLS_OK',len(cases))
