#!/usr/bin/env python3
"""Validate explicitly pinned generic KeyPath patterns in stripped Swift images.

Layout: swift-6.3.3 IRGen/GenKeyPath.cpp, ABI/GenericContext.h and
SwiftShims/swift/shims/KeyPath.h. No byte-pattern scan is used by reconstruction.
Only the generic pattern prefix and bounded buffer are accepted here;
this does not execute or claim full component semantics.
"""
import struct
import hashlib

def validate(read, sections, patterns):
    records = []
    if len(patterns) != len(set(patterns)) or len(patterns) > 16384:
        raise ValueError('Invalid pinned Swift KeyPath pattern list')
    def inside(name, address, length=1):
        return any(section == name and start <= address and address + length <= start + size
                   for segment, section, start, size in sections if segment == '__TEXT')
    for pattern in patterns:
        if pattern % 4 or not inside('__const', pattern, 24):
            raise ValueError('Swift KeyPath pattern outside original constant section')
        once, env_delta, root_delta, leaf_delta, kvc, header = struct.unpack('<5iI', read(pattern, 24))
        if once or not env_delta:
            raise ValueError('Unsupported Swift KeyPath pattern prefix')
        env = pattern + 4 + env_delta
        if env % 4 or not inside('__swift5_typeref', env, 4):
            raise ValueError('Swift KeyPath environment outside typeref section')
        types = []
        for offset, delta in [(8, root_delta), (12, leaf_delta)]:
            target = pattern + offset + delta
            # GenKeyPath.cpp adds one to the mangled-name address; the runtime
            # removes the tag before resolving it. Metadata references are
            # not necessarily prefixed with the 0xff role marker.
            if not delta or not target & 1 or not inside('__swift5_typeref', target - 1):
                raise ValueError('Invalid Swift KeyPath mangled type reference')
            if not read(target - 1, 1)[0]:
                raise ValueError('Empty Swift KeyPath mangled type reference')
            types.append(target - 1)
        if kvc:
            kvc_target = pattern + 16 + kvc
            if not any(start <= kvc_target < start + size for _, _, start, size in sections):
                raise ValueError('Swift KeyPath KVC name outside original image')
            payload = read(kvc_target, 256).split(b'\0', 1)[0]
            if len(payload) == 256:
                raise ValueError('Unbounded Swift KeyPath KVC name')
            payload.decode('utf-8')
        size = header & 0x00ffffff
        if header & 0x1f000000 or not 0 <= size <= 4096 or size % 4 or not inside('__const', pattern + 24, size):
            raise ValueError('Invalid Swift KeyPath buffer extent or reserved flags')
        if size:
            component = struct.unpack('<I', read(pattern + 24, 4))[0]
            if (component >> 24) & 0x7f not in (0, 1, 2, 3, 4):
                raise ValueError('Invalid Swift KeyPath first component kind')
        elif types[0] != types[1]:
            raise ValueError('Identity Swift KeyPath has distinct root and leaf types')
        records.append(dict(pattern=hex(pattern), environment=hex(env),
                            root_type=hex(types[0]), leaf_type=hex(types[1]), buffer_size=size))
    return records


def validate_bounds(read, patterns, bounds):
    """Accept only exact original environment bytes ending at an independent type label.

    GenProto.cpp records reqs.size(), while GenMeta.cpp omits marker protocols.
    Original compiler IR reproduces this overcount. Do not rewrite its header,
    or read the next mangled type as another requirement.
    """
    environments={int(p['environment'],16) for p in patterns}
    labels={int(p[k],16) for p in patterns for k in ('root_type','leaf_type')}
    result={}
    for entry in bounds:
        start,end=int(entry['start'],16),int(entry['end'],16)
        if start in result or start not in environments or end not in labels or not 4<=end-start<=65536:
            raise ValueError('Invalid pinned Swift KeyPath environment boundary')
        if hashlib.sha256(read(start,end-start)).hexdigest()!=entry['sha256']:
            raise ValueError('Pinned Swift KeyPath environment bytes changed')
        result[start]=end
    return result
