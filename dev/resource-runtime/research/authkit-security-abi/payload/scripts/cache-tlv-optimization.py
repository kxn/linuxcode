#!/usr/bin/env python3
"""Validate Apple's x86_64 cache TLV_Thunkv2 transformation, never a generic addend.

The rule is documented in apple-dyld/cache_builder/NewSharedCacheBuilder.cpp
optimizeTLVs and libdyld/threadLocalHelpers.s. Standalone restoration must use
the normal bootstrap and disk descriptor ABI, not bind the optimized +8 entry.
"""
import struct


def validate(ns, original, slot, export, target, expected, flags):
    if (export['symbol'] != '__tlv_bootstrap' or flags != 0
            or export['provider'] != '/usr/lib/system/libdyld.dylib'
            or target != expected+8):
        raise ValueError('Not an original optimized TLV bootstrap relocation')
    bootstrap = ns['resolve']('/usr/lib/libSystem.B.dylib', '__tlv_bootstrap')
    if bootstrap != expected or export['implementation'] != expected:
        raise ValueError('Optimized TLV bootstrap export identity differs')
    descriptors = [(start, size) for _, _, start, size, attributes in original.sections
                   if attributes & 255 == 0x13 and size]
    owners = [(start, size) for start, size in descriptors
              if start <= slot and slot+24 <= start+size]
    if len(owners) != 1 or owners[0][1] % 24 or (slot-owners[0][0]) % 24:
        raise ValueError('Optimized TLV location is not a complete descriptor head')
    template = [(attributes & 255, start, size)
                for _, _, start, size, attributes in original.sections
                if attributes & 255 in (0x11, 0x12) and size]
    if not template:
        raise ValueError('Optimized TLV has no Mach-O template')
    start = min(address for _, address, _ in template)
    length = max(address+size for _, address, size in template)-start
    raw = ns['read'](slot, 24)
    key, offset, delta, initial_size = struct.unpack('<IIiI', raw[8:])
    initialized = any(kind == 0x11 for kind, _, _ in template)
    expected_delta = start-(slot+16) if initialized else 0
    if initial_size != length or delta != expected_delta or offset >= length:
        raise ValueError('Optimized TLV fields differ from original template bounds')
    return dict(slot=hex(slot), bootstrap=hex(bootstrap), optimized_entry=hex(target),
        template_start=hex(start), template_size=length, variable_offset=offset,
        cache_key=key, template_delta=delta, raw_original_descriptor=raw.hex(),
        requires_disk_ABI_restoration=True)
