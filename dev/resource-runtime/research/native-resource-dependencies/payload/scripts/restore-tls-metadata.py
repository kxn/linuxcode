#!/usr/bin/env python3
"""Undo Apple's cache TLV_Thunkv2 optimization for Darling's disk TLV ABI.

Layouts: Apple dyld libdyld/ThreadLocalVariables.h and cache builder optimizeTLVs;
Darling dyld src/threadLocalVariables.c. Only the pinned x86_64 images are used.
"""
import struct

def restore(segments,ns,store,binds,obj):
    sections=[]
    for segment in segments:
        for section in segment['sections']:
            flags=struct.unpack_from('<I',section,64)[0]&255
            if flags in (0x11,0x12,0x13):
                address,size=struct.unpack_from('<QQ',section,32)
                sections.append((flags,address,size))
    descriptors=[(address,size) for flags,address,size in sections if flags==0x13 and size]
    if not descriptors:return set(),None
    template=sorted((address,size) for flags,address,size in sections if flags in (0x11,0x12) and size)
    if not template:raise ValueError('TLS descriptors without a template')
    start=template[0][0];length=max(address+size for address,size in template)-start
    nonzero=any(flags==0x11 and size for flags,address,size in sections)
    ordinal=obj.dependencies.index('/usr/lib/libSystem.B.dylib')+1
    bootstrap=ns['resolve']('/usr/lib/libSystem.B.dylib','__tlv_bootstrap')
    modified=set();restored=[]
    for address,size in descriptors:
        if size%24:raise ValueError('Unexpected TLS descriptor size')
        for slot in range(address,address+size,24):
            thunk=ns['pointer'](slot)
            if thunk==bootstrap+8:
                key,offset,delta,initial_size=struct.unpack('<IIiI',ns['read'](slot+8,16))
                expected_delta=start-(slot+16) if nonzero else 0
                if initial_size!=length or delta!=expected_delta:
                    raise ValueError('Cache TLS template differs from Mach-O sections')
            elif thunk==bootstrap:
                key,offset=struct.unpack('<QQ',ns['read'](slot+8,16))
                if key:raise ValueError('Nonzero key in an unoptimized disk TLS descriptor')
            else:raise ValueError('Unknown cached TLS thunk')
            if offset>=length:raise ValueError('TLS variable offset outside template')
            store(slot,0);binds[slot]=('__tlv_bootstrap',ordinal,False,0)
            store(slot+8,0);store(slot+16,offset)
            modified.update((slot,slot+8,slot+16))
            restored.append({'offset':hex(slot-obj.base),'template_offset':offset,
                'zero_fill':any(flags==0x12 and a-start<=offset<a-start+s for flags,a,s in sections)})
    return modified,{'variables':len(restored),'template_size':length,'descriptors':restored}
