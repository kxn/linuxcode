#!/usr/bin/env python3
"""Validate the compiler-proven Codable/Hashable/Sendable environment extent.

Only the four-declared, three-emitted standard-protocol layout is accepted.
Both bounds come from original local symbols. Original headers stay unchanged.
"""
import hashlib
import struct

ENVIRONMENT = '_generic environment SeRzSERzSHRzs8SendableRzl'
PROTOCOLS = [('_$sSeMp', b'Decodable'), ('_$sSEMp', b'Encodable'), ('_$sSHMp', b'Hashable')]

def validate(ns, sections, environments, symbols, records):
    result = {}
    locations = {}
    for row in symbols: locations.setdefault(row['name'], set()).add(int(row['address'], 16))
    def inside(address, length):
        return any(segment == '__TEXT' and name == '__swift5_typeref' and
            start <= address and address + length <= start + size for segment,name,start,size in sections)
    for record in records:
        start,end = int(record['start'],16),int(record['end'],16)
        if (start in result or start not in environments or start % 4 or end-start != 44 or
            record['environment_symbol'] != ENVIRONMENT or not record['next_symbol'].startswith('_symbolic ') or
            locations.get(ENVIRONMENT) != {start} or locations.get(record['next_symbol']) != {end} or
            not inside(start,end-start)):
            raise ValueError('Invalid marker-environment labels or extent')
        if any(start < int(row['address'],16) < end for row in symbols
               if row['name'].startswith(('_generic environment ', '_symbolic '))):
            raise ValueError('Marker environment crosses an independent type label')
        data = ns['read'](start,end-start)
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Marker environment bytes changed')
        if struct.unpack_from('<IHBB',data) != (16385,1,128,0):
            raise ValueError('Unsupported marker-environment generic header')
        parameters = set()
        for index,(symbol,name) in enumerate(PROTOCOLS):
            offset = 8+12*index
            flags,type_delta,protocol_delta = struct.unpack_from('<Iii',data,offset)
            if flags != 128 or not protocol_delta or protocol_delta & 2:
                raise ValueError('Unsupported marker-environment protocol requirement')
            parameter = start+offset+4+type_delta; parameters.add(parameter)
            if not inside(parameter,2) or ns['read'](parameter,2) != b'x\0' or parameter not in locations.get('_symbolic x',set()):
                raise ValueError('Marker-environment parameter reference differs')
            protocol = start+offset+8+(protocol_delta & ~3)
            if protocol_delta & 1: protocol = ns['pointer'](protocol)
            expected = ns['resolve']('/usr/lib/swift/libswiftCore.dylib',symbol)
            if not expected or protocol != expected or struct.unpack('<I',ns['read'](protocol,4))[0] & 31 != 3:
                raise ValueError('Marker-environment standard protocol identity differs')
            delta = struct.unpack('<i',ns['read'](protocol+8,4))[0]
            if ns['read'](protocol+8+delta,len(name)+1) != name+b'\0':
                raise ValueError('Marker-environment protocol name differs')
        if len(parameters) != 1: raise ValueError('Marker environment uses different parameters')
        result[start] = end
    return result
