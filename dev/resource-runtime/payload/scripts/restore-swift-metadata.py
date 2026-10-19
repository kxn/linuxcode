#!/usr/bin/env python3
"""Experimental x86_64 Swift relative-reference recovery.

Layouts: swift-6.3.3-RELEASE ABI/{Metadata,GenericContext}.h and
RemoteInspection/Records.h. Reject unhandled layouts and external direct
references. This is staging only; semantic tests are still required.
"""
import struct
import runpy
from pathlib import Path

def restore(segments,ns,allocate,store,classify,own):
    read,pointer=ns['read'],ns['pointer']
    sections={section[:16].split(b'\0')[0].decode():struct.unpack_from('<QQ',section,32)
        for segment in segments for section in segment['sections']}
    patches=[];cells={};contexts=set();patterns=set();conformances=set();generic_count=0
    resilient_metaclasses=set();resilient_class_ro=set();class_overrides=[];generic_packs=[]
    conformance_packs=[]
    def u32(address):return struct.unpack('<I',read(address,4))[0]
    def write32(address,value):
        for segment in segments:
            off=address-segment['base']
            if 0<=off<=len(segment['content'])-4:
                struct.pack_into('<i',segment['content'],off,value);return
        raise ValueError('Swift relative-reference write outside image')
    protocol_definitions={}
    address,length=sections.get('__objc_protolist',(0,0))
    for offset in range(0,length,8):
        protocol=pointer(address+offset)
        if own(protocol):protocol_definitions[read(pointer(protocol+8),512).split(b'\0')[0]]=protocol
    def bound_cell(target,objc_protocol=False):
        if objc_protocol and not own(target):
            name=read(pointer(target+8),512).split(b'\0')[0]
            if name not in protocol_definitions:raise ValueError('Swift reference to nonlocal Objective-C protocol '+repr(name))
            target=protocol_definitions[name]
        if target not in cells:
            cell=allocate(bytes(8));classify(cell,target);cells[target]=cell
        return cells[target]
    def relative(slot,mode='direct',label=''):
        value=struct.unpack('<i',read(slot,4))[0]
        if not value:return 0
        mask=3 if mode=='protocol' else (1 if mode=='indirectable' else 0)
        target=slot+(value&~mask)
        if own(target):return target
        flags=value&mask
        if mode in ('indirectable','protocol'):
            pointee=pointer(target) if flags&1 else target
            replacement=bound_cell(pointee,mode=='protocol' and bool(flags&2))
            flags|=1
        elif mode in ('slot','objc-slot'):
            try:replacement=bound_cell(pointer(target),mode=='objc-slot')
            except ValueError as error:
                raise ValueError(f'Swift {label} at {slot:#x}, original cell {target:#x}: {error}') from error
        else:raise ValueError(f'Unsupported external direct Swift reference {label} at {slot:#x} -> {target:#x}')
        delta=replacement-slot
        if not -(1<<31)<=delta<(1<<31) or delta&mask:raise ValueError('Swift relative reference cannot reach recovery cell')
        write32(slot,delta|flags)
        patches.append({'slot':hex(slot),'kind':mode,'field':label,'original_target':hex(target)})
        return target
    def requirement(address):
        kind=u32(address)&31
        relative(address+4,label='generic parameter type')
        if kind==0:relative(address+8,'protocol','generic protocol')
        elif kind in (1,2,4):relative(address+8,label='generic type constraint')
        elif kind==3:relative(address+8,'indirectable','generic conformance')
        elif kind not in (5,31):raise ValueError('Unsupported Swift generic requirement kind '+str(kind))
    def pattern(address,kind):
        if not address or address in patterns:return
        patterns.add(address)
        relative(address,label='metadata instantiator');relative(address+4,label='metadata completer')
        flags=u32(address+8)
        if kind==16:
            relative(address+12,label='heap destructor');relative(address+16,label='ivar destructor')
            cursor=address+32
        else:
            relative(address+12,'indirectable','generic value witnesses');cursor=address+16
        for present in (bool(flags&1),kind==16 and bool(flags&(1<<31))):
            if present:
                relative(cursor,label='metadata partial pattern');cursor+=8
    def generic(header,kind):
        nonlocal generic_count
        generic_count+=1
        relative(header,label='metadata instantiation cache')
        target=relative(header+4,label='metadata pattern')
        pattern(target,kind)
        return generic_signature(header+8)
    def generic_signature(header):
        params,requirements,keys,flags=struct.unpack('<4H',read(header,8))
        if flags&~1:raise ValueError(f'Unsupported Swift generic-context extensions {flags:#x} at {header:#x}')
        if params>256 or requirements>256:raise ValueError('Invalid Swift generic-context bounds')
        parameters=read(header+8,params)
        cursor=(header+8+params+3)&~3
        requirement_flags=[u32(cursor+12*i) for i in range(requirements)]
        for _ in range(requirements):requirement(cursor);cursor+=12
        if flags&1:
            # GenericContext.h: the aligned requirements are followed by a
            # 4-byte GenericPackShapeHeader and NumPacks 8-byte descriptors.
            # These fields contain integers only; no pointers are fabricated.
            packs,shapes=struct.unpack('<2H',read(cursor,4));cursor+=4
            expected=sum((p&0xbf)==0x81 for p in parameters)
            expected+=sum((r&0xa0)==0xa0 for r in requirement_flags)
            if not 0<shapes<=packs==expected<=512:
                raise ValueError('Invalid Swift generic pack shape header')
            entries=[];previous=(-1,-1)
            for _ in range(packs):
                kind,index,shape,reserved=struct.unpack('<4H',read(cursor,8))
                if kind not in (0,1) or index>=keys or shape>=shapes or reserved:
                    raise ValueError('Invalid Swift generic pack shape descriptor')
                if (kind,index)<=previous:
                    raise ValueError('Unordered Swift generic pack shape descriptors')
                previous=(kind,index)
                entries.append({'kind':kind,'index':index,'shape_class':shape});cursor+=8
            if not own(cursor-1):raise ValueError('Swift generic pack table exceeds image')
            generic_packs.append({'header':hex(header),'shape_classes':shapes,'entries':entries})
        return cursor
    def context(address):
        if not address or not own(address) or address in contexts:return
        contexts.add(address);flags=u32(address);kind=flags&31;specific=flags>>16
        parent=relative(address+4,'indirectable','context parent')
        # An indirect parent refers to a pointer cell, not another descriptor.
        parent_value=struct.unpack('<i',read(address+4,4))[0]
        if parent_value&1 and parent:parent=pointer(parent)
        context(parent)
        if kind==0:relative(address+8,label='module name');return
        if kind==1:
            relative(address+8,label='extension context type')
            if flags&128:generic_signature(address+12)
            return
        if kind==2:
            cursor=generic_signature(address+8) if flags&128 else address+8
            if specific&1:relative(cursor,label='anonymous context name')
            return
        if kind==3:
            relative(address+8,label='protocol name')
            signature_count=u32(address+12);requirement_count=u32(address+16)
            if max(signature_count,requirement_count)>4096:raise ValueError('Invalid Swift protocol descriptor bounds')
            relative(address+20,label='protocol associated type names')
            cursor=address+24
            for _ in range(signature_count):requirement(cursor);cursor+=12
            for _ in range(requirement_count):relative(cursor+4,label='protocol default implementation');cursor+=8
            return
        if kind not in (16,17,18):raise ValueError('Unsupported Swift context descriptor kind '+str(kind))
        relative(address+8,label='type name');relative(address+12,label='metadata accessor')
        relative(address+16,label='type field descriptor')
        cursor=address+(44 if kind==16 else 28)
        if kind==16:relative(address+20,label='superclass type')
        if flags&128:cursor=generic(cursor,kind)
        if specific&8:raise ValueError('Unsupported Swift metadata prespecialization list')
        if kind==16 and specific&0x40:raise ValueError(f'Unsupported Swift class default override table at {address:#x}')
        resilient=kind==16 and bool(specific&0x2000)
        if resilient:
            relative(address+24,label='resilient class metadata bounds')
            superclass_kind=(specific>>9)&7
            if superclass_kind>3:raise ValueError('Unsupported resilient superclass reference kind')
            relative(cursor,'slot' if superclass_kind in (1,3) else 'direct','resilient superclass')
            cursor+=4
        initialization=specific&3
        if initialization==1:
            for off in (0,4,8):
                target=relative(cursor+off,label='singleton initialization')
                if resilient and off==4 and target:
                    for field in (0,4,8):relative(target+field,label='resilient class pattern function')
                    ro=relative(target+16,label='resilient class pattern ro')
                    metaclass=relative(target+20,label='resilient class pattern metaclass')
                    if ro:resilient_class_ro.add(ro)
                    if metaclass:resilient_metaclasses.add(metaclass)
            cursor+=12
        elif initialization==2:relative(cursor,label='foreign initialization');cursor+=4
        elif initialization!=0:raise ValueError('Unsupported Swift metadata initialization')
        if kind==16 and specific&0x8000:
            count=u32(cursor+4)
            if count>4096:raise ValueError('Invalid Swift vtable size')
            cursor+=8
            for _ in range(count):relative(cursor+4,label='class method implementation');cursor+=8
        if kind==16 and specific&0x4000:
            # Swift 6.3.3 ABI/Metadata.h: TargetOverrideTableHeader is a
            # uint32 count; each 12-byte TargetMethodOverrideDescriptor has
            # two relative-indirectable pointers and a compact implementation
            # pointer (an ordinary relative code/data pointer on x86_64).
            count=u32(cursor);cursor+=4
            if count>4096 or (count and not own(cursor+12*count-1)):
                raise ValueError('Invalid Swift method override table extent')
            for _ in range(count):
                relative(cursor,'indirectable','override base class')
                relative(cursor+4,'indirectable','override base method')
                relative(cursor+8,label='override implementation')
                class_overrides.append({'class_descriptor':hex(address),'entry':hex(cursor)})
                cursor+=12
        if resilient and u32(address+28)&1:
            relative(cursor,label='Objective-C resilient class stub')
    def conformance(address):
        if address in conformances:return
        conformances.add(address)
        flags=u32(address+12);kind=(flags>>3)&7
        relative(address,'indirectable','conformance protocol')
        relative(address+4,'slot' if kind in (1,3) else 'direct','conformance type')
        if kind>3:raise ValueError('Unsupported Swift conformance type kind')
        relative(address+8,label='witness table pattern')
        cursor=address+16
        if flags&64:relative(cursor,'indirectable','retroactive context');cursor+=4
        for _ in range((flags>>8)&255):requirement(cursor);cursor+=12
        pack_count=flags>>24
        if pack_count:
            # Metadata.h places the integer-only pack descriptors between the
            # conditional requirements and the resilient witness header.
            entries=[];previous=(-1,-1)
            for _ in range(pack_count):
                pack_kind,index,shape,reserved=struct.unpack('<4H',read(cursor,8))
                if pack_kind not in (0,1) or reserved or (pack_kind,index)<=previous:
                    raise ValueError('Invalid Swift conditional pack shape descriptor')
                previous=(pack_kind,index)
                entries.append({'kind':pack_kind,'index':index,'shape_class':shape});cursor+=8
            if not own(cursor-1):raise ValueError('Swift conditional pack table exceeds image')
            conformance_packs.append({'conformance':hex(address),'entries':entries})
        if flags&0x10000:
            count=u32(cursor);cursor+=4
            if count>4096:raise ValueError('Invalid resilient witness count')
            for _ in range(count):
                relative(cursor,'indirectable','resilient witness requirement')
                relative(cursor+4,label='resilient witness implementation');cursor+=8
        if flags&0x20000:
            relative(cursor+4,label='witness instantiator');relative(cursor+8,label='witness private data');cursor+=12
        if flags&0x80000:relative(cursor,label='global actor type')
    for name in ('__swift5_types','__swift5_types2','__swift5_proto'):
        address,length=sections.get(name,(0,0))
        if length%4:raise ValueError('Unaligned Swift record section')
        for offset in range(0,length,4):
            slot=address+offset
            if name in ('__swift5_types','__swift5_types2'):
                raw=struct.unpack('<i',read(slot,4))[0];kind=raw&3;target=slot+(raw&~3)
                if kind==1:target=pointer(target)
                elif kind!=0:raise ValueError('Unsupported Swift type record')
                if not own(target):raise ValueError('External Swift type record')
                context(target)
            else:conformance(relative(slot,label='protocol conformance record'))
    address,length=sections.get('__swift5_protos',(0,0))
    for offset in range(0,length,4):
        slot=address+offset;raw=struct.unpack('<i',read(slot,4))[0]
        if raw&2:raise ValueError('Unsupported reserved Swift protocol-record flag')
        target=relative(slot,'indirectable','protocol definition record')
        if raw&1 and target:target=pointer(target)
        context(target)
    # Reflection descriptors reference mangled strings and names. Their
    # variable-length records are validated before any relative field is read.
    for name in ('__swift5_fieldmd','__swift5_assocty','__swift5_capture','__swift5_builtin','__swift5_mpenum'):
        cursor,length=sections.get(name,(0,0));end=cursor+length
        while cursor<end:
            if name=='__swift5_fieldmd':
                if cursor+16>end:raise ValueError('Truncated Swift field descriptor')
                _,size,count=struct.unpack('<HHI',read(cursor+8,8))
                if size!=12:raise ValueError('Unsupported Swift field record size')
                total=16+size*count
                if cursor+total>end:raise ValueError('Swift field records exceed section')
                relative(cursor,label='field mangled type');relative(cursor+4,label='field superclass')
                for index in range(count):
                    record=cursor+16+size*index
                    relative(record+4,label='field type');relative(record+8,label='field name')
            elif name=='__swift5_assocty':
                count,size=struct.unpack('<II',read(cursor+8,8));total=16+count*size
                if size!=8 or cursor+total>end:raise ValueError('Invalid associated type records')
                relative(cursor,label='associated conforming type');relative(cursor+4,label='associated protocol type')
                for index in range(count):
                    relative(cursor+16+8*index,label='associated type name')
                    relative(cursor+20+8*index,label='associated substituted type')
            elif name=='__swift5_capture':
                captures,sources,bindings=struct.unpack('<III',read(cursor,12));total=12+captures*4+sources*8
                if cursor+total>end:raise ValueError('Swift capture records exceed section')
                for offset in range(12,total,4):relative(cursor+offset,label='capture/source type')
            elif name=='__swift5_builtin':total=20;relative(cursor,label='builtin type')
            else:total=4+4*(u32(cursor+4)>>16);relative(cursor,label='multi-payload enum type')
            if total<=0 or cursor+total>end:raise ValueError('Swift reflection record exceeds section')
            cursor+=total
    start,length=sections.get('__swift5_typeref',(0,0));data=read(start,length) if length else b'';index=0
    symbolic_count=0;environments={}
    original_sections=[(section[16:32].split(b'\0')[0].decode(),
                        section[:16].split(b'\0')[0].decode(),
                        *struct.unpack_from('<QQ',section,32))
                       for segment in segments for section in segment['sections']]
    keypath_module=runpy.run_path(str(Path(__file__).with_name('swift-keypath-environment-records.py')))
    keypaths=keypath_module['validate'](
        read,ns.get('swift_original_sections',original_sections),ns.get('swift_keypath_patterns',[]))
    keypath_bounds=keypath_module['validate_bounds'](read,keypaths,ns.get('swift_keypath_environment_bounds',[]))
    overstated_keypath_requirements=[]
    environment_addresses=list(ns.get('swift_generic_environments',[]))
    environment_addresses += [int(record['environment'],16) for record in keypaths]
    for address in sorted(set(environment_addresses)):
        if not start<=address<start+length:
            raise ValueError('Swift generic environment outside typeref section')
        # GenericContext.h TargetGenericEnvironment: flags, cumulative
        # uint16 parameter counts, byte descriptors, aligned requirements.
        flags=u32(address);levels=flags&0xfff;count=(flags>>12)&0xffff
        if flags>>28 or not 0<levels<=256 or count>4096:
            raise ValueError('Invalid Swift generic environment flags')
        counts=struct.unpack('<'+'H'*levels,read(address+4,2*levels))
        if tuple(sorted(counts))!=counts or counts[-1]>256:
            raise ValueError('Invalid Swift generic environment parameter counts')
        cursor=address+4+2*levels
        if any(p&0x40 or (p&0x3f)>2 for p in read(cursor,counts[-1])):
            raise ValueError('Invalid Swift generic environment parameters')
        cursor=(cursor+counts[-1]+3)&~3
        if cursor+12*count>start+length:
            raise ValueError('Swift generic environment exceeds typeref section')
        if address in keypath_bounds:
            end=keypath_bounds[address]
            if not cursor<=end<cursor+12*count or (end-cursor)%12:
                raise ValueError('Pinned Swift KeyPath boundary does not shorten whole requirements')
            actual=(end-cursor)//12
            overstated_keypath_requirements.append({'environment':hex(address),
                'declared':count,'emitted':actual,'original_header_preserved':True})
            count=actual
        for _ in range(count):requirement(cursor);cursor+=12
        environments[address]=cursor
    environment_ranges=sorted(environments.items())
    if any(a[1]>b[0] for a,b in zip(environment_ranges,environment_ranges[1:])):
        raise ValueError('Overlapping Swift generic environments')
    while index<len(data):
        if start+index in environments:
            index=environments[start+index]-start;continue
        kind=data[index]
        if 1<=kind<=23:
            if index+5>len(data):raise ValueError('Truncated Swift symbolic reference')
            symbolic_count+=1
            if kind==2:relative(start+index+1,'slot','symbolic indirect context')
            elif kind==12:relative(start+index+1,'objc-slot','symbolic Objective-C protocol')
            # docs/ABI/Mangling.rst also defines 0x08 as a direct
            # associated-conformance accessor relative to the conforming
            # type. Preserve local references; external direct ones still
            # fail in relative(), and no accessor invocation is synthesized.
            elif kind in (1,7,8,9,10,11):
                target=relative(start+index+1,label='symbolic direct reference')
                if kind==1:context(target)
            else:raise ValueError(f'Unsupported Swift symbolic reference kind {kind} at {start+index:#x}: {data[max(0,index-16):index+24].hex()}')
            index+=5
        elif 24<=kind<=31:raise ValueError('Unsupported absolute Swift symbolic reference')
        else:index+=1
    return {'contexts':len(contexts),'generic_contexts':generic_count,'patterns':len(patterns),
        'resilient_objc_metaclasses':sorted(resilient_metaclasses),
        'resilient_objc_class_ro':sorted(resilient_class_ro),
        'class_method_overrides':class_overrides,
        'generic_pack_shapes':generic_packs,
        'conditional_pack_shapes':conformance_packs,
        'generic_environments':[{'start':hex(a),'end':hex(b)} for a,b in environment_ranges],
        'pinned_keypath_patterns':keypaths,
        'overstated_keypath_requirements':overstated_keypath_requirements,
        'conformances':len(conformances),'symbolic_references':symbolic_count,
        'recovery_cells':len(cells),'patches':patches,'execution_verified':False,
        'scope':'Experimental relative-reference recovery for the accepted layouts; not a claim of full Swift image compatibility.'}
