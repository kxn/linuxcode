#!/usr/bin/env python3
"""Validate pinned environment extents containing an emitted ~Copyable record.

Swift 6.3.3 GenProto.cpp stores reqs.size() in an environment header, while
GenMeta.cpp addGenericRequirements also emits inverse requirements. Keep those
original bytes/header; recover only the exact independently labelled extent.
This intentionally supports the verified one-parameter, one-protocol case.
"""
import hashlib
import struct

def validate(read, sections, environments, symbols, records):
    result = {}
    if not records:
        return result
    locations = {}
    for symbol in symbols:
        locations.setdefault(symbol['name'], set()).add(int(symbol['address'], 16))
    def inside(address, size):
        return any(segment == '__TEXT' and name == '__swift5_typeref'
                   and start <= address and address + size <= start + length
                   for segment, name, start, length in sections)
    for record in records:
        start, end = int(record['start'], 16), int(record['end'], 16)
        name, next_name = record['environment_symbol'], record['next_symbol']
        if (start in result or start not in environments or start % 4 or end % 4
                or not name.startswith('_generic environment ')
                or not next_name.startswith('_symbolic ')
                or locations.get(name) != {start} or locations.get(next_name) != {end}
                or not inside(start, end-start) or end-start != 32):
            raise ValueError('Invalid pinned inverse-environment labels or extent')
        if any(start < address < end for symbol in symbols
               if symbol['name'].startswith('_symbolic ')
               for address in [int(symbol['address'], 16)]):
            raise ValueError('Inverse environment crosses a symbolic type label')
        data = read(start, end-start)
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Pinned inverse-environment bytes changed')
        flags, count, parameter, padding = struct.unpack_from('<IHBB', data)
        if (flags, count, parameter, padding) != (4097, 1, 128, 0):
            raise ValueError('Unsupported inverse-environment generic header')
        requirement, type_delta, protocol_delta = struct.unpack_from('<Iii', data, 8)
        inverse, inverse_delta, index, mask = struct.unpack_from('<IiHH', data, 20)
        # A protocol requirement contributes its real witness-table argument.
        # The additional inverse descriptor suppresses Copyable for parameter 0.
        if requirement != 128 or not protocol_delta:
            raise ValueError('Unsupported inverse-environment protocol requirement')
        protocol = start + 16 + protocol_delta
        if (protocol_delta & 3 or not any(segment=='__TEXT' and name in ('__const', '__constg_swiftt')
                and base<=protocol and protocol+24<=base+size
                for segment,name,base,size in sections)
                or struct.unpack('<I',read(protocol,4))[0]&31 != 3):
            raise ValueError('Inverse-environment protocol reference differs')
        if inverse != 5 or index != 0 or mask != 1:
            raise ValueError('Unsupported inverse-environment inverse descriptor')
        target = start + 12 + type_delta
        if (target != start + 24 + inverse_delta or not inside(target, 2)
                or read(target, 2) != b'x\0'
                or target not in locations.get('_symbolic x', set())):
            raise ValueError('Inverse-environment parameter reference differs')
        result[start] = end
    return result
