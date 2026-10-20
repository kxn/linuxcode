#!/usr/bin/env python3
"""Reject validly encoded but incorrect exports in a real constant facade."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args();out=root/args.output;assert not out.exists()
pin=json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
original=root/('runtime/fullsystem-libraries'+pin['path'])
candidate=root/('runtime/rebuilt-'+args.target)/Path(pin['path']).name
before,after=original.read_bytes(),candidate.read_bytes()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(original)==pin['sha256']
module=runpy.run_path(str(root/'scripts/original-reexport-facade.py'))
positive=module['inspect'](before,after)
assert positive['original_version_constants_byte_equal']
layout=module['layout'](after)
raw=next(raw for k,at,raw in layout['commands'] if k==0x80000022)
expoff,size=struct.unpack_from('<II',raw,40);blob=after[expoff:expoff+size]
helper=runpy.run_path(str(root/'scripts/macho-named-reexport.py'))
exports=helper['entries'](blob);name,payload=next(iter(exports.items()))
assert payload[0]==0 and len(payload)>1
at=blob.index(payload);assert blob.count(payload)==1
bad=bytearray(after);bad[expoff+at]=4
cases=[('strong_version_export_changed_to_weak',bad)]
bad=bytearray(after);bad[expoff+at+1]^=1
cases.append(('version_export_points_to_different_data',bad))
edge=b'Number';at=blob.index(edge)
bad=bytearray(after);bad[expoff+at]=ord('M')
cases.append(('version_export_name_changed',bad))
rejected=[]
for name,damaged in cases:
    # These export tries still parse. Reject their identity, not just broken
    # stream syntax or an unrelated changed constant section.
    changed=helper['entries'](bytes(damaged[expoff:expoff+size]));assert changed!=exports
    try:module['inspect'](before,bytes(damaged))
    except (ValueError,AssertionError,struct.error):rejected.append(name)
    else:raise AssertionError('Accepted '+name)
assert module['inspect'](before,after)==positive
report=dict(verified=True,target=args.target,rejected_actual_export_mutations=rejected,
            malformed_export_syntax_used=False,no_binary_copies_written=True,
            original_sha256=sha(original),candidate_sha256=sha(candidate),runtime_behavior_verified=False,
            sources={n:sha(root/n) for n in [str(Path(__file__).relative_to(root)),
                'scripts/original-reexport-facade.py','scripts/macho-named-reexport.py']})
out.write_text(json.dumps(report,indent=2)+'\n');print('REAL_CONSTANT_FACADE_EXPORT_IDENTITY_CONTROLS_OK',len(rejected))
