#!/usr/bin/env python3
"""Use real linked images to verify absent streams are unchanged and sorting survives."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--empty-image', required=True)
parser.add_argument('--prior-normalizer', required=True)
parser.add_argument('--weak-image', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
out = root/args.output
assert not out.exists()
current = runpy.run_path(str(root/'scripts/normalize-macho-weak-bind.py'))
previous = runpy.run_path(str(root/args.prior_normalizer))

def weak(data):
    at = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, at)
        if command in [0x22, 0x80000022]:
            return struct.unpack_from('<II', data, at+24)
        at += size
    raise AssertionError('No classic dyld information')

empty = (root/args.empty_image).read_bytes()
assert weak(empty) == (0,0)
new, proof = current['normalize'](empty)
assert new == empty and proof['no_weak_bind_stream'] and proof['linkedit_payload_shift'] == 0
rejected = False
try:
    previous['normalize'](empty)
except AssertionError:
    rejected = True
assert rejected, 'The historical normalizer no longer reproduces this failure'
data = (root/args.weak_image).read_bytes()
off, size = weak(data)
assert size
normalized, ordered = current['normalize'](data)
next_off, next_size = weak(normalized)
assert current['decode'](data[off:off+size]) == current['decode'](normalized[next_off:next_off+next_size])
assert ordered['all_symbol_flags_and_bindings_preserved']
assert ordered['instructions_and_other_payloads_unchanged']
assert ordered['following_linkedit_payload_preserved_byte_for_byte']
sha = lambda path: hashlib.sha256((root/path).read_bytes()).hexdigest()
report = dict(verified=True,empty_stream_image_byte_equal=True,historical_failure_reproduced=True,
    nonempty_stream_all_binding_records_preserved=True,no_images_written=True,
    inputs={path:sha(path) for path in [args.empty_image,args.prior_normalizer,args.weak_image,
        'scripts/normalize-macho-weak-bind.py','scripts/test-empty-weak-normalization.py']},
    empty_stream_proof=proof,nonempty_stream_proof=ordered)
out.write_text(json.dumps(report,indent=2)+'\n')
print('VERIFIED',args.output)
