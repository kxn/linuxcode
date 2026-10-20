#!/usr/bin/env python3
"""Verify a named original stub/GOT import through actual reexport edges.

Equal function addresses never establish symbol identity. The original cache
patch record must name the terminal export reached from the selected dependency.
This reader emits no library and accepts only zero-addend, strong pooled cells.
"""
from pathlib import Path
import hashlib
import runpy
import struct


def verify(ns, image_path, target, slots, symbol, provider, library_root):
    image = ns['image'](image_path)
    assert provider in image.dependencies
    slots = [int(slot, 16) if isinstance(slot, str) else slot for slot in slots]
    assert slots and len(set(slots)) == len(slots) and all(slot % 8 == 0 for slot in slots)
    ordinal = image.dependencies.index(provider)+1

    def route(path, name, seen=frozenset()):
        assert (path, name) not in seen, 'Cyclic original reexport route'
        seen = seen | {(path, name)}
        owner = ns['image'](path)
        value = owner.exports.get(name)
        step = dict(provider=path, symbol=name)
        if value is not None:
            if value[0] == 'address':
                return value[1], [{**step, 'kind': 'address', 'export': list(value)}]
            assert value[0] == 'reexport' and 1 <= value[1] <= len(owner.dependencies)
            dependency = owner.dependencies[value[1]-1]
            found = route(dependency, value[2] or name, seen)
            assert found is not None
            address, tail = found
            return address, [{**step, 'kind': 'symbol-reexport', 'ordinal': value[1],
                              'dependency': dependency, 'export': list(value)}, *tail]
        for dependency in owner.reexports:
            assert dependency in owner.dependencies
            found = route(dependency, name, seen)
            if found is not None:
                address, tail = found
                return address, [{**step, 'kind': 'whole-library-reexport',
                    'ordinal': owner.dependencies.index(dependency)+1,
                    'dependency': dependency}, *tail]
        return None

    found = route(provider, symbol)
    assert found is not None and found[0] == target == ns['resolve'](provider, symbol)
    chain = found[1]
    terminal = chain[-1]
    assert terminal['kind'] == 'address'
    stubs = []
    for _, _, start, size, flags in image.sections:
        if flags & 255 != 8:
            continue
        assert size % 6 == 0
        for address in range(start, start+size, 6):
            code = ns['read'](address, 6)
            assert code[:2] == bytes.fromhex('ff25')
            slot = address+6+struct.unpack_from('<i', code, 2)[0]
            if slot in slots:
                assert ns['pointer'](slot) == target
                stubs.append(dict(address=hex(address), slot=hex(slot), bytes=code.hex()))
    assert set(slots) == {int(row['slot'], 16) for row in stubs}, 'Import lacks original stub'
    reader = runpy.run_path(str(Path(__file__).with_name('cache-patch-metadata.py')))
    metadata = reader['read_image_bindings'](ns, image_path,
        {target: [(symbol, ordinal, False)]}, follow_renamed_reexports=True)
    records = [row for row in metadata['got_records'] if row['slot'] in slots]
    assert len(records) == len(slots) and {row['slot'] for row in records} == set(slots)
    for row in records:
        assert row['provider'] == terminal['provider'] and row['symbol'] == terminal['symbol']
        assert row['implementation'] == row['target'] == target
        assert row['addend'] == row['high7'] == 0 and not row['weak_import']
        assert row['matching_import_names'] == [symbol]
    paths = {image_path, *[step['provider'] for step in chain]}
    hashes = {path: hashlib.sha256((Path(library_root)/path.lstrip('/')).read_bytes()).hexdigest()
              for path in sorted(paths)}
    return dict(kind='original-stub-GOT-and-reexport-route', target=hex(target),
        slots=[hex(slot) for slot in slots], selected=[symbol, provider], stubs=stubs,
        route=chain, original_file_sha256=hashes,
        patch_info_sha256=metadata['patch_info_sha256'], records=records)
