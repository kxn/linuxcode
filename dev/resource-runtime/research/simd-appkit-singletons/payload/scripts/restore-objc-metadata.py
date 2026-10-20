#!/usr/bin/env python3
"""Restore Objective-C metadata for explicitly pinned x86_64 cache images.

Convert cache-relative method lists to ordinary pointer lists and reset caches.
Layouts are taken from Apple's objc4 and Darling's objc4 source. No Swift or
external protocol/class metadata copying is attempted.
"""
import struct
import subprocess
from pathlib import Path

def restore(segments,ns,allocate,store,classify,binds,rebases,own,objc_ordinal,project,expected_classes,
            additional_classes=(),additional_ro=(),additional_only=False):
    read,pointer=ns['read'],ns['pointer']
    sections={}
    for segment in segments:
        for section in segment['sections']:
            name=section[:16].split(b'\0')[0].decode()
            sections[name]=struct.unpack_from('<QQ',section,32)
    modified=set();string_values={};methods={};properties=set();protocols=set();ivar_lists=set()
    relative_lists=[];long_strings=[]
    coalesced_protocols={}

    def write_bytes(address,payload):
        for segment in segments:
            offset=address-segment['base']
            if 0<=offset and offset+len(payload)<=len(segment['content']):
                segment['content'][offset:offset+len(payload)]=payload;return
        raise ValueError('Objective-C metadata write outside image')
    def local_pointer(slot,target):
        store(slot,target)
        if target:rebases[slot]=target
        modified.add(slot)
    def cstring(address):
        if not address:return 0
        # Nested aggregate ivar encodings in Network exceed 4 KiB. Read a
        # bounded, NUL-terminated sequence rather than truncating that real
        # type encoding or treating the remainder as another metadata object.
        payload=bytearray()
        for offset in range(0,1048576,256):
            chunk=read(address+offset,256)
            end=chunk.find(b'\0')
            payload.extend(chunk if end<0 else chunk[:end])
            if end>=0:break
        else:raise ValueError(f'Unbounded metadata string at {address:#x}')
        payload=bytes(payload)
        if len(payload)>=4096:long_strings.append({'address':hex(address),'length':len(payload)})
        if payload not in string_values:string_values[payload]=allocate(payload+b'\0',1)
        return string_values[payload]
    def string_slot(slot):local_pointer(slot,cstring(pointer(slot)))
    def base_list(slot,kind):
        address=pointer(slot)
        if not address&1:return address
        # Apple NewSharedCacheBuilder category emission puts
        # category lists first and the original base list last. Each category
        # remains in its defining image's __objc_catlist and is registered by
        # Darling when that image loads. Restore only the original base here.
        header=address&~1
        size,count=struct.unpack('<II',read(header,8))
        if size!=8 or not 1<=count<=4096:raise ValueError('Unsupported relative list-of-lists header')
        entry=header+8+8*(count-1)
        raw=struct.unpack('<Q',read(entry,8))[0]
        delta=raw>>16
        if delta&(1<<47):delta-=1<<48
        target=entry+delta
        if not own(target):
            # The builder uses a shared empty method list, or a zero entry
            # pointing to itself for an absent protocol/property base list.
            payload=read(target,8)
            empty=struct.unpack('<Q',payload)[0]==0 if kind=='protocol' else struct.unpack('<I',payload[4:])[0]==0
            if not empty:raise ValueError('Nonempty external base list is unsupported')
            target=0
        local_pointer(slot,target)
        relative_lists.append({'kind':kind,'categories':count-1,'base_empty':not bool(target)})
        return target
    def pointers(section_name):
        address,size=sections.get(section_name,(0,0))
        if size%8:raise ValueError('Unaligned Objective-C pointer section')
        return [pointer(address+i) for i in range(0,size,8)]
    local_protocols={read(pointer(address+8),512).split(b'\0')[0]:address
                     for address in pointers('__objc_protolist') if own(address)}

    # Version 16 of libobjc's legacy cache optimization header supplies the
    # selector base used by the current cache's small-direct method entries.
    objc_source=ns['cache']['library_root']/'usr/lib/libobjc.A.dylib'
    symbols=subprocess.check_output(['llvm-nm-19','--defined-only',str(objc_source)],text=True)
    opt=next(int(line.split()[0],16) for line in symbols.splitlines()
             if line.split() and line.split()[-1]=='__objc_opt_data')
    if struct.unpack('<I',read(opt,4))[0]!=16:raise ValueError('Unsupported Objective-C selector cache version')
    selector_base=opt+struct.unpack('<q',read(opt+40,8))[0]
    if read(selector_base,5)!=b'\xf0\x9f\xa4\xaf\0':raise ValueError('Unexpected shared selector base marker')

    def method_list(address,protocol=False):
        if not address:return 0,0
        if address in methods:return methods[address]
        if not own(address):raise ValueError(f'External method-list metadata is unsupported: {address:#x}')
        flags,count=struct.unpack('<II',read(address,8))
        if count>4096:raise ValueError('Unexpected method-list count')
        small=bool(flags&0x80000000)
        size=flags&~0xffff0003
        if size!=(12 if small else 24):raise ValueError('Unsupported method-list entry size')
        target=allocate(struct.pack('<II',24,count)+bytes(count*24))
        methods[address]=(target,count)
        for index in range(count):
            source=address+8+index*size;dest=target+8+index*24
            if small:
                name_off,type_off,imp_off=struct.unpack('<iii',read(source,12))
                name=selector_base+name_off if flags&0x40000000 else pointer(source+name_off)
                types=source+4+type_off if type_off else 0
                implementation=source+8+imp_off if imp_off else 0
            else:
                name,types,implementation=(pointer(source+i) for i in (0,8,16))
                # Retain a valid copy of the original big list too. Its slots
                # remain in the cache pointer chains even after class_ro is
                # redirected to the ordinary method-list allocation below.
                local_pointer(source,cstring(name));local_pointer(source+8,cstring(types))
                classify(source+16,implementation);modified.add(source+16)
                write_bytes(address,struct.pack('<I',24))
            local_pointer(dest,cstring(name));local_pointer(dest+8,cstring(types))
            if protocol and not implementation:local_pointer(dest+16,0)
            else:
                classify(dest+16,implementation)
                modified.add(dest+16)
        return target,count
    def method_slot(slot,protocol=False):
        try:target,count=method_list(pointer(slot),protocol)
        except ValueError as error:raise ValueError(f'Method-list slot {slot:#x}: {error}') from error
        local_pointer(slot,target)
        return count
    def property_list(address):
        if not address or address in properties:return
        if not own(address):raise ValueError('External property metadata is unsupported')
        properties.add(address)
        size,count=struct.unpack('<II',read(address,8))
        if size!=16 or count>4096:raise ValueError('Unsupported property list')
        for index in range(count):
            string_slot(address+8+16*index);string_slot(address+16+16*index)
    def protocol_list(address):
        if not address:return
        if not own(address):raise ValueError('External protocol-list metadata is unsupported')
        count=struct.unpack('<Q',read(address,8))[0]
        if count>4096:raise ValueError('Unexpected protocol-list length')
        for index in range(count):
            slot=address+8+8*index;original=pointer(slot)
            restored=protocol_object(original)
            if restored!=original:local_pointer(slot,restored)
    def protocol_object(address):
        if not address:return 0
        if not own(address):
            # The cache canonicalizes references, while retaining this image's
            # real original protocol definition in __objc_protolist.
            name=read(pointer(address+8),512).split(b'\0')[0]
            if name not in local_protocols:raise ValueError('External protocol metadata lacks a local definition')
            coalesced_protocols[address]=(local_protocols[name],name.decode('utf-8'))
            address=local_protocols[name]
        if address in protocols:return address
        protocols.add(address)
        size,flags=struct.unpack('<II',read(address+64,8))
        # Both Apple's and Darling's objc4 reserve bits 0..15 for Swift.
        # A Swift-defined @objc protocol carries the IsSwift bit (0); retain
        # that semantic bit, while still rejecting cache/runtime state flags.
        if size!=96 or flags not in (0,1):raise ValueError('Unsupported protocol layout or cache flags')
        string_slot(address+8);protocol_list(pointer(address+16))
        count=sum(method_slot(address+offset,True) for offset in (24,32,40,48))
        property_list(pointer(address+56))
        extended=pointer(address+72)
        if extended:
            if not own(extended):raise ValueError('External extended method-type array')
            for index in range(count):string_slot(extended+8*index)
        string_slot(address+80);property_list(pointer(address+88))
        return address
    def ivar_list(address):
        if not address or address in ivar_lists:return
        if not own(address):raise ValueError('External ivar metadata is unsupported')
        ivar_lists.add(address)
        size,count=struct.unpack('<II',read(address,8))
        if size!=32 or count>4096:raise ValueError('Unsupported ivar list')
        for index in range(count):
            string_slot(address+16+32*index);string_slot(address+24+32*index)

    classes=pointers('__objc_classlist')
    all_classes=set(classes)|{pointer(address) for address in classes}
    if len(classes)!=expected_classes or len(all_classes)!=2*expected_classes:raise ValueError('Unexpected Objective-C class count')
    original_classes=set(all_classes)
    original_ro={pointer(address+32)&~7 for address in original_classes}
    all_classes=(set(additional_classes)-original_classes) if additional_only else all_classes|set(additional_classes)
    class_names=[]
    restored_ro=set()
    def restore_ro(ro):
        if ro in restored_ro:return
        restored_ro.add(ro)
        if not own(ro):raise ValueError('External class_ro metadata is unsupported')
        for offset in (16,24,56):string_slot(ro+offset)
        original_methods=base_list(ro+32,'method')
        if original_methods:
            # method_slot reads reference bytes, so use the decoded address
            # directly after undoing a cache list-of-lists tag.
            target,count=method_list(original_methods)
            local_pointer(ro+32,target)
        protocol_list(base_list(ro+40,'protocol'))
        ivar_list(pointer(ro+48));property_list(base_list(ro+64,'property'))
    for address in sorted(all_classes):
        if not own(address):raise ValueError('External class metadata is unsupported')
        # A normal on-disk class starts with objc_empty_cache, not a precomputed
        # shared-cache dispatch table. The runtime realizes its flags itself.
        store(address+16,0);binds[address+16]=('__objc_empty_cache',objc_ordinal,False,0)
        store(address+24,0);modified.update((address+16,address+24))
        ro=pointer(address+32)&~7
        if not own(ro):raise ValueError('External class_ro metadata is unsupported')
        flags=struct.unpack('<I',read(ro,4))[0]
        name=read(pointer(ro+24),512).split(b'\0')[0].decode()
        if not flags&1 and address in original_classes:class_names.append(name)
        restore_ro(ro)
    for ro in sorted(set(additional_ro)-(original_ro if additional_only else set())):restore_ro(ro)
    for category in pointers('__objc_catlist'):
        if not own(category):raise ValueError('External category metadata is unsupported')
        string_slot(category)
        method_slot(category+16);method_slot(category+24)
        protocol_list(pointer(category+32));property_list(pointer(category+40));property_list(pointer(category+48))
    for protocol in pointers('__objc_protolist'):protocol_object(protocol)
    # Protocol availability references are canonicalized separately from class
    # conformance lists. Point them at the same restored local definitions.
    if '__objc_protorefs' in sections:
        start,size=sections['__objc_protorefs']
        for offset in range(0,size,8):
            slot=start+offset;local_pointer(slot,protocol_object(pointer(slot)))
    info,size=sections['__objc_imageinfo']
    if size!=8:raise ValueError('Unexpected Objective-C image-info size')
    flags=struct.unpack('<I',read(info+4,4))[0]
    # Bit 0 changed meaning between Apple's new and Darling's older runtime.
    # Neither the cache-category bit nor any other preoptimization applies here.
    write_bytes(info+4,struct.pack('<I',flags&~(1|8|16|128)))
    return modified,{'classes':sorted(class_names),'method_lists':len(methods),
                     'methods':sum(value[1] for value in methods.values()),
                     'protocols':len(protocols),'strings_copied':len(string_values),
                     'selector_base':hex(selector_base),'relative_list_lists':relative_lists,
                     'coalesced_protocols':[{'original':hex(original),'local':hex(local),'name':name}
                         for original,(local,name) in sorted(coalesced_protocols.items())],
                     'long_metadata_strings':long_strings}
