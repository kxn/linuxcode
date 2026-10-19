#!/usr/bin/env python3
"""Check the real constant alias and reject a changed cell, address and identity."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audit', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root/args.output
assert not output.exists()
audit = json.loads((root/args.audit).read_text())
row = next(row for row in audit['rows'] if row.get('same_trivial_property_alias'))
module = runpy.run_path(str(root/'scripts/verify-original-constant-alias.py'))
ns = runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
address = int(row['target'],16)
proof = row['constant_alias_proof']
assert module['verify'](ns,address,row['exports'],proof['selected_provider'],root) == proof
cases = []
for name, changed_address, choices in [('wrong-address',address+4,row['exports']),
    ('wrong-name',address,[[row['exports'][0][0]+'_wrong',row['exports'][0][1]],row['exports'][1]])]:
    rejected = False
    try: module['verify'](ns,changed_address,choices,proof['selected_provider'],root)
    except AssertionError: rejected = True
    assert rejected
    cases.append(dict(mode=name,rejected=True))
with tempfile.TemporaryDirectory(prefix='constant-alias-negative-',dir=root/'runtime') as folder:
    content = bytearray((root/proof['selected_provider']).read_bytes())
    segments,_,_ = runpy.run_path(str(root/'scripts/inspect-preserved-patch-got.py'))['macho'](content)
    at = int(proof['selected_export_address'],16)
    segment = next(segment for segment in segments if segment[1]<=at<segment[1]+segment[2])
    offset = segment[3]+at-segment[1]
    struct.pack_into('<I',content,offset,1)
    candidate = Path(folder)/'changed-constant'
    candidate.write_bytes(content)
    rejected = False
    try: module['verify'](ns,address,row['exports'],str(candidate.relative_to(root)),root)
    except AssertionError: rejected = True
    assert rejected
    cases.append(dict(mode='changed-constant-word',rejected=True))
record = dict(verified=True,cases=cases,audit=args.audit,
    audit_sha256=hashlib.sha256((root/args.audit).read_bytes()).hexdigest(),
    original_and_selected_alias_identity_verified=True,runtime_identity_verified=False,
    sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in [
        'scripts/test-resource-constant-alias.py','scripts/verify-original-constant-alias.py']})
output.write_text(json.dumps(record,indent=2)+'\n')
print('CONSTANT_ALIAS_REAL_IDENTITY_AND_THREE_NEGATIVE_CONTROLS_OK')
