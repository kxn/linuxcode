#!/usr/bin/env python3
"""Read exact v4 identities for original symbol-stub cells absent from a candidate's imports."""
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
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
pin = json.loads((root/'config/coregraphics-image-pins.json').read_text())[args.target]
original = root/'runtime/fullsystem-libraries'/pin['path'].lstrip('/')
assert sha(original) == pin['sha256']
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
image = ns['image'](pin['path'])
data = original.read_bytes()
imports = {}
at = 32
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    command, length = struct.unpack_from('<II', data, at)
    if command == 2:
        symoff, count, stroff, strsize = struct.unpack_from('<4I', data, at+8)
        for index in range(count):
            start, kind, _, desc, _ = struct.unpack_from('<IBBHQ', data, symoff+16*index)
            if kind & 0xe or not kind & 1: continue
            assert start < strsize
            name = data[stroff+start:data.index(0, stroff+start, stroff+strsize)].decode()
            ordinal = desc >> 8
            assert 0 <= ordinal <= len(image.dependencies)
            address = ns['resolve'](image.dependencies[ordinal-1] if ordinal else pin['path'], name)
            assert address is not None
            imports.setdefault(address, []).append((name, ordinal, bool(desc & 0x40)))
    at += length
for name, provider in pin.get('cache_imports', {}).items():
    assert provider in image.dependencies
    address = ns['resolve'](provider, name)
    assert address is not None
    imports.setdefault(address, []).append((name, image.dependencies.index(provider)+1, False))
reader = runpy.run_path(str(root/'scripts/cache-patch-metadata.py'))
metadata = reader['read_image_bindings'](ns, pin['path'], imports,
    follow_renamed_reexports=pin.get('patch_got_renamed_reexports', False))
covered = {record['slot'] for record in metadata['got_records']}
wanted = {}
for name, segment, start, size, flags in image.sections:
    if flags & 255 != 8: continue
    assert size % 6 == 0
    for address in range(start, start+size, 6):
        encoded = ns['read'](address, 6)
        assert encoded[:2] == b'\xff\x25'
        slot = address+6+struct.unpack_from('<i', encoded, 2)[0]
        if slot not in covered: wanted.setdefault(slot, []).append(address)

# Read exact location/name records, including names not in the client's nlist.
# This inventory never chooses an alias, changes imports or emits a library.
context = ns['cache']['contexts'][0]
header = context.header
table = ns['read'](header.patchInfoAddr, header.patchInfoSize)
version, locations, *fields = struct.unpack_from('<II18Q', table)
assert (version, locations) == (4, 0)
descriptions = [('images',16), ('exports',8), ('clients',12), ('client_exports',12),
    ('locations',8), ('names',1), ('got_clients',8), ('got_exports',12), ('got_locations',16)]
arrays = {}
for i, (name, stride) in enumerate(descriptions):
    offset, count = fields[2*i]-header.patchInfoAddr, fields[2*i+1]
    assert 152 <= offset and count <= len(table)//stride and offset+count*stride <= len(table)
    arrays[name] = offset, count, stride
def row(name, index, fmt):
    offset, count, stride = arrays[name]
    assert 0 <= index < count
    return struct.unpack_from(fmt, table, offset+index*stride)
records = []
for provider_index, source_image in enumerate(context.images):
    first, count = row('got_clients', provider_index, '<II')
    _, _, export_start, export_count = row('images', provider_index, '<IIII')
    for i in range(first, first+count):
        export_index, start, count = row('got_exports', i, '<III')
        assert export_start <= export_index < export_start+export_count
        implementation, name_flags = row('exports', export_index, '<II')
        name_offset = name_flags & 0x0fffffff
        assert name_offset < arrays['names'][1]
        name_at = arrays['names'][0]+name_offset
        name = table[name_at:table.index(0, name_at, arrays['names'][0]+arrays['names'][1])].decode()
        provider = context.readString(source_image.pathFileOffset).rstrip(b'\0').decode()
        implementation += source_image.address
        for j in range(start, start+count):
            offset, flags, padding = row('got_locations', j, '<QII')
            slot = header.sharedRegionStart+offset
            if slot not in wanted: continue
            assert not flags & 1 and padding == 0 and not (flags >> 1) & 0x7f
            addend = flags >> 9
            assert ns['pointer'](slot) == implementation+addend
            assert ns['resolve'](provider, name) == implementation
            records.append(dict(slot=hex(slot), stubs=[hex(address) for address in wanted[slot]],
                symbol=name, provider=provider, implementation=hex(implementation), addend=addend,
                weak_import=bool(flags & 0x100), provider_index=provider_index,
                export_index=export_index, location_index=j))
report = dict(diagnostic_only=True, target=args.target, original_image_sha256=sha(original),
    patch_info_sha256=hashlib.sha256(table).hexdigest(), uncovered_cells=len(wanted), records=records,
    missing_metadata=sorted(hex(slot) for slot in set(wanted)-{int(record['slot'],16) for record in records}),
    source_sha256=sha(Path(__file__)), image_emitted=False)
output.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(dict(output=args.output, uncovered_cells=len(wanted), identities=len(records),
    missing_metadata=len(report['missing_metadata']))))
