#!/usr/bin/env python3
"""Diagnose original x86 symbol stubs not covered by cache patch GOT records.

Read-only evidence: no candidate is emitted and no relocation is inferred.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = root/args.output
assert not output.exists()
pin = json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
assert pin['reference_set'] == 'fullsystem'
data = (root/('runtime/fullsystem-libraries'+pin['path'])).read_bytes()
assert hashlib.sha256(data).hexdigest() == pin['sha256']
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
image = ns['image'](pin['path'])
imports = {}
at = 32
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    command, size = struct.unpack_from('<II', data, at)
    if command == 2:
        symoff, count, stroff, strsize = struct.unpack_from('<4I', data, at+8)
        for index in range(count):
            start, kind, _, desc, value = struct.unpack_from('<IBBHQ', data, symoff+16*index)
            if kind & 0xe or not kind & 1:
                continue
            name = data[stroff+start:data.index(0, stroff+start, stroff+strsize)].decode()
            ordinal = desc >> 8
            provider = image.dependencies[ordinal-1] if ordinal else pin['path']
            address = ns['resolve'](provider, name)
            assert address is not None, (provider, name)
            imports.setdefault(address, []).append((name, ordinal, bool(desc & 0x40)))
    at += size
metadata = runpy.run_path(str(root/'scripts/cache-patch-metadata.py'))['read_image_bindings'](
    ns, pin['path'], imports, follow_renamed_reexports=True)
got = {row['slot'] for row in metadata['got_records']}

def section(address):
    return [dict(name=name, segment=segment, start=hex(start), size=size, flags=hex(flags))
            for name, segment, start, size, flags in image.sections if start <= address < start+size]

uncovered = []
for name, segment, start, size, flags in image.sections:
    if flags & 255 != 8:
        continue
    assert size % 6 == 0
    for address in range(start, start+size, 6):
        encoded = ns['read'](address, 6)
        assert encoded[:2] == bytes.fromhex('ff25')
        slot = address+6+struct.unpack_from('<i', encoded, 2)[0]
        if slot in got:
            continue
        value = ns['pointer'](slot)
        uncovered.append(dict(stub=hex(address), slot=hex(slot), raw=ns['read'](slot, 8).hex(),
            decoded_target=hex(value), slot_sections=section(slot), target_sections=section(value)))
report = dict(target=args.target, original_sha256=pin['sha256'], original_patch_GOT_cells=len(got),
    uncovered_stubs=uncovered, diagnostic_only=True, candidate_emitted=False,
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
output.write_text(json.dumps(report, indent=2)+'\n')
print('UNCOVERED', len(uncovered), args.output)
