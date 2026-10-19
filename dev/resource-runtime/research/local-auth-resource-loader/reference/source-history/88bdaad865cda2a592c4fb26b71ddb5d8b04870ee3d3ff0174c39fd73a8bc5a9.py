#!/usr/bin/env python3
"""Corrupt in-memory copies of actual candidates and require independent inspection to reject them."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import runpy
import struct

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', action='append', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root/args.output
assert not output.exists()
module = runpy.run_path(str(root/'scripts/inspect-preserved-patch-got.py'))
pins = json.loads((root/'config/coregraphics-image-pins.json').read_text())
cases = []
for target in args.target:
    pin = pins[target]
    original = (root/'runtime/fullsystem-libraries'/pin['path'].lstrip('/')).read_bytes()
    folder = root/('runtime/rebuilt-'+target)
    candidate = (folder/Path(pin['path']).name).read_bytes()
    report = json.loads((folder/'reconstruction.json').read_text())
    assert hashlib.sha256(original).hexdigest() == pin['sha256'] == report['original_image_sha256']
    assert hashlib.sha256(candidate).hexdigest() == report['staged_image_sha256']
    result = module['inspect'](original,candidate,report)
    assert result['original_code_bytes_equal']
    segments,sections,_ = module['macho'](candidate)
    original_segments,_,_ = module['macho'](original)
    base = next(segment[1] for segment in original_segments if segment[0] == '__TEXT')
    start,size,offset,flags = next(value for value in sections.values() if value[1] and value[3] & 0x80000400)
    altered = bytearray(candidate)
    altered[offset] ^= 1
    rejected = False
    try: module['inspect'](original,altered,report)
    except AssertionError: rejected = True
    assert rejected, 'Executable corruption accepted'
    row = dict(target=target,candidate_sha256=report['staged_image_sha256'],
        positive_inspection=result,changed_code_rejected=True)
    references = report['byte_preserving_patch_got'].get('address_references',[])
    if references:
        address = int(references[0]['slot'],16)-base
        segment = next(segment for segment in segments if segment[1] <= address < segment[1]+segment[2])
        offset = segment[3]+address-segment[1]
        altered = bytearray(candidate)
        struct.pack_into('<Q',altered,offset,struct.unpack_from('<Q',altered,offset)[0]+8)
        rejected = False
        try: module['inspect'](original,altered,report)
        except AssertionError: rejected = True
        assert rejected, 'Wrong pooled-cell address accepted'
        row['changed_GOT_address_rejected'] = True
    local = report['byte_preserving_patch_got'].get('original_local_stub_cells',[])
    nulls=[cell for cell in local if cell.get('original_null')]
    if nulls:
        address=int(nulls[0]['slot'],16)-base
        segment=next(segment for segment in segments if segment[1]<=address<segment[1]+segment[2])
        offset=segment[3]+address-segment[1]
        altered=bytearray(candidate);struct.pack_into('<Q',altered,offset,1)
        rejected=False
        try: module['inspect'](original,altered,report)
        except AssertionError: rejected=True
        assert rejected,'Changed original NULL cell accepted'
        row['changed_original_NULL_cell_rejected']=True
    if local and 'symbol' in local[0]:
        changed = copy.deepcopy(report)
        changed['byte_preserving_patch_got']['original_local_stub_cells'][0]['symbol'] = '_intentionally_wrong_binding'
        rejected = False
        try: module['inspect'](original,candidate,changed)
        except AssertionError: rejected = True
        assert rejected, 'False local binding proof accepted'
        row['false_local_binding_proof_rejected'] = True
    cases.append(row)
record = dict(verified=True,cases=cases,no_binary_copies_written=True,runtime_behavior_verified=False,
    sources={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in [
        'scripts/test-preserved-patch-got-binaries.py','scripts/inspect-preserved-patch-got.py']})
output.write_text(json.dumps(record,indent=2)+'\n')
print('ACTUAL_CANDIDATES_CODE_DATA_REFERENCE_AND_BINDING_PROOF_CORRUPTION_REJECTED',len(cases))
