#!/usr/bin/env python3
"""Read original v4 dyld patch records without inferring nearby symbol names.

Layout and addend semantics: Apple's pinned common/CachePatching.h/.cpp,
recorded in config/cache-patch-metadata-format.json. This reader does not
modify images, cache files, code, or runtime bindings.
"""
import hashlib
import struct
from pathlib import Path
import runpy

def read_image_bindings(ns, image_path, pooled_imports=None, follow_renamed_reexports=False):
    context = ns['cache']['contexts'][0]
    header = context.header
    address, length = header.patchInfoAddr, header.patchInfoSize
    if not address or length < 152:
        raise ValueError('Missing complete v4 patch header')
    data = ns['read'](address, length)
    version, location_version, *fields = struct.unpack_from('<II18Q', data)
    if version != 4 or location_version != 0:
        raise ValueError('Unsupported dyld patch table/location version')
    descriptions = [('images', 16), ('exports', 8), ('clients', 12),
        ('client_exports', 12), ('locations', 8), ('names', 1),
        ('got_clients', 8), ('got_exports', 12), ('got_locations', 16)]
    arrays = {}
    for i, (name, stride) in enumerate(descriptions):
        start, count = fields[2*i:2*i+2]
        offset = start - address
        if offset < 152 or count > length // stride or offset + count*stride > length:
            raise ValueError('Patch array exceeds original table: ' + name)
        arrays[name] = (offset, count, stride)
    images = context.images
    if len(images) != arrays['images'][1] or arrays['got_clients'][1] != len(images):
        raise ValueError('Patch/cache image indexes disagree')
    original = ns['image'](image_path)
    indexes = [i for i, image in enumerate(images) if image.address == original.base]
    if len(indexes) != 1:
        raise ValueError('Original image has no unique patch index')
    client_index = indexes[0]

    def row(name, index, fmt):
        offset, count, stride = arrays[name]
        if not 0 <= index < count or struct.calcsize(fmt) != stride:
            raise ValueError('Invalid patch index/layout: ' + name)
        return struct.unpack_from(fmt, data, offset + index*stride)

    def span(name, start, count):
        if start < 0 or count < 0 or start + count > arrays[name][1]:
            raise ValueError('Invalid patch subrange: ' + name)
        return range(start, start + count)

    def export_record(provider_index, export_index):
        implementation, name_flags = row('exports', export_index, '<II')
        names, names_size, _ = arrays['names']
        offset = name_flags & 0x0fffffff
        if offset >= names_size:
            raise ValueError('Patch symbol name exceeds string table')
        end = data.find(b'\0', names + offset, names + names_size)
        if end < 0:
            raise ValueError('Unterminated patch symbol name')
        symbol = data[names+offset:end].decode('utf-8')
        provider = context.readString(images[provider_index].pathFileOffset).rstrip(b'\0').decode()
        return dict(symbol=symbol, provider=provider, kind=name_flags >> 28,
            implementation=images[provider_index].address + implementation)

    records = []
    got_records = []
    optimized_tlv_records = []
    def export_route(path, name, seen=None):
        seen = set() if seen is None else seen
        if (path, name) in seen:
            return None
        seen = seen | {(path, name)}
        image = ns['image'](path)
        canonical = getattr(image, 'path', path)
        value = image.exports.get(name)
        if value:
            if value[0] == 'address':
                return [(canonical, name, value[1])]
            return export_route(image.dependencies[value[1]-1], value[2] or name, seen)
        for dependency in image.reexports:
            route = export_route(dependency, name, seen)
            if route:
                return route
        return None

    def matching_names(export):
        names = set()
        candidates = pooled_imports.get(export['implementation'], [])
        if any(name == export['symbol'] for name, _, _ in candidates):
            return [export['symbol']]
        for name, ordinal, weak in candidates:
            if name == export['symbol']:
                names.add(name)
            elif follow_renamed_reexports:
                if not 0 <= ordinal <= len(original.dependencies):
                    raise ValueError('Invalid original import ordinal for reexport')
                provider = original.dependencies[ordinal-1] if ordinal else image_path
                route = export_route(provider, name)
                expected_provider = getattr(ns['image'](export['provider']), 'path', export['provider'])
                if route and route[-1] == (expected_provider, export['symbol'], export['implementation']):
                    names.add(name)
        return sorted(names)
    for provider_index in range(len(images)):
        client_start, client_count, export_start, export_count = row('images', provider_index, '<IIII')
        span('exports', export_start, export_count)
        for i in span('clients', client_start, client_count):
            selected, first, count = row('clients', i, '<III')
            if selected >= len(images):
                raise ValueError('Invalid client image index')
            if selected != client_index:
                continue
            for j in span('client_exports', first, count):
                export_index, location_start, location_count = row('client_exports', j, '<III')
                if not export_start <= export_index < export_start + export_count:
                    raise ValueError('Client export does not belong to its provider')
                export = export_record(provider_index, export_index)
                for k in span('locations', location_start, location_count):
                    offset, flags = row('locations', k, '<II')
                    if flags & 1:
                        raise ValueError('Authenticated patch location needs another ABI reader')
                    high7 = (flags >> 1) & 0x7f
                    addend = flags >> 9
                    slot = original.base + offset
                    target = ns['pointer'](slot)
                    expected = (export['implementation'] + addend) | (high7 << 57)
                    resolved = ns['resolve'](export['provider'], export['symbol'])
                    if target != expected:
                        if export['symbol'] != '__tlv_bootstrap' or target != expected+8:
                            raise ValueError('Original pointer differs from its patch relocation')
                        validator = runpy.run_path(str(Path(__file__).with_name('cache-tlv-optimization.py')))['validate']
                        proof = validator(ns, original, slot, export, target, expected, flags)
                        if resolved != export['implementation']:
                            raise ValueError('Optimized TLV provider export differs')
                        # This is not a normal symbol-plus-addend binding.
                        # The separate TLS restorer must consume it and emit
                        # the disk ABI bootstrap/key/offset layout instead.
                        optimized_tlv_records.append(proof)
                        continue
                    if resolved != export['implementation']:
                        raise ValueError('Patch symbol does not resolve to its recorded implementation')
                    aliases = ({'matching_import_names': matching_names(export)}
                               if follow_renamed_reexports and pooled_imports is not None else {})
                    records.append({**export, **aliases, 'slot': slot, 'addend': addend,
                        'weak_import': bool(flags & 0x100), 'high7': high7,
                        'target': target, 'target_matches_patch': target == expected,
                        'export_matches_patch': resolved == export['implementation'],
                        'provider_index': provider_index, 'export_index': export_index,
                        'location_index': k})
        if pooled_imports is not None:
            first, count = row('got_clients', provider_index, '<II')
            for j in span('got_exports', first, count):
                export_index, location_start, location_count = row('got_exports', j, '<III')
                if not export_start <= export_index < export_start + export_count:
                    raise ValueError('GOT export does not belong to its provider')
                export = export_record(provider_index, export_index)
                names = matching_names(export)
                if not names:
                    continue
                for k in span('got_locations', location_start, location_count):
                    offset, flags, padding = row('got_locations', k, '<QII')
                    slot = header.sharedRegionStart + offset
                    # x86_64 instructions can only reach a pooled GOT cell
                    # through a signed 32-bit displacement. Other subcaches
                    # contain additional pools for the same symbols.
                    executable = [(start, size) for _, _, start, size, flags in original.sections
                                  if flags & 0x80000400]
                    if not any(start - (1 << 31) <= slot < start + size + (1 << 31)
                               for start, size in executable):
                        continue
                    if flags & 1 or padding:
                        raise ValueError('Unsupported authenticated/padded x86 GOT relocation')
                    high7 = (flags >> 1) & 0x7f
                    addend = flags >> 9
                    target = ns['pointer'](slot)
                    expected = (export['implementation'] + addend) | (high7 << 57)
                    resolved = ns['resolve'](export['provider'], export['symbol'])
                    if target != expected or resolved != export['implementation'] or high7:
                        raise ValueError('Original GOT relocation fails pointer/export verification')
                    aliases = {'matching_import_names': names} if follow_renamed_reexports else {}
                    got_records.append({**export, **aliases, 'slot': slot, 'addend': addend,
                        'weak_import': bool(flags & 0x100), 'high7': high7,
                        'target': target, 'target_matches_patch': True,
                        'export_matches_patch': True, 'provider_index': provider_index,
                        'export_index': export_index, 'location_index': k})
    return dict(version=version, location_version=location_version, image_index=client_index,
        patch_info_address=address, patch_info_bytes=length,
        patch_info_sha256=hashlib.sha256(data).hexdigest(), records=records,
        got_records=got_records, optimized_tlv_records=optimized_tlv_records)

def exact_imports(records, imports, pooled=False):
    """Resolve only exact original nlist names at the metadata's implementation.

    The caller may already have selected a compatibility provider for that
    original import. Preserve its ordinal and the actual relocation addend.
    Never identify an import by proximity to an exported address.
    """
    result = {}
    for record in records:
        if not record['target_matches_patch'] or not record['export_matches_patch'] or record['high7']:
            raise ValueError('Unverified or tagged patch relocation')
        # A pooled cell is shared with other images, whose weak-import flags
        # can differ. Its symbol/implementation is authoritative; the exact
        # nlist entry retains this reconstructed image's own weak semantics.
        names = record.get('matching_import_names', [record['symbol']])
        matches = set(item for item in imports.get(record['implementation'], [])
            if item[0] in names and (pooled or item[2] == record['weak_import']))
        if len(matches) != 1:
            raise ValueError('Patch relocation has no unique original import: ' + record['symbol'])
        binding = (*next(iter(matches)), record['addend'])
        if record['slot'] in result and result[record['slot']] != binding:
            raise ValueError('Conflicting patch relocations for one original slot')
        result[record['slot']] = binding
    return result

def addend_imports(metadata, imports):
    return exact_imports([record for record in metadata['records'] if record['addend']], imports)
