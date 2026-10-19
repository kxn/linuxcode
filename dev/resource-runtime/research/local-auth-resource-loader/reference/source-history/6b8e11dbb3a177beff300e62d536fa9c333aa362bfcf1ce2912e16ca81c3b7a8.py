#!/usr/bin/env python3
"""Standalone reconstruction of specifically supported x86_64 cache images.

Recover cache pointers, pooled GOT references, selectors and classic dyld binds.
Only writes a staged library; it is never installed by this script. This is
restricted to pinned images with explicitly supported metadata layouts. Swift
recovery requires explicit experimental flags and separate runtime validation;
this is not a general Swift/ObjC extractor.
"""
from pathlib import Path
import hashlib
import json
import re
import runpy
import struct
import subprocess
import sys
import argparse
from bisect import bisect_right

project=Path(__file__).resolve().parent.parent
target_manifest=json.loads((project/'config/cache-image-pins.json').read_text())
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',choices=sorted(target_manifest),required=True)
parser.add_argument('--modern-adapter',action='store_true')
parser.add_argument('--lazy-functions',action='store_true',help='Restore lazy binding for original lazy-pointer sections and pooled symbol stubs')
parser.add_argument('--reference-set',choices=['recovery','fullsystem'])
parser.add_argument('--experimental-swift',action='store_true',help='Stage an unverified Swift-image experiment; never implies Swift metadata compatibility')
parser.add_argument('--analyze-code',action='store_true',help='Use original function entries and validated x86 jump-table analysis for a C/ObjC image')
parser.add_argument('--repair-swift-relative',action='store_true',help='Experimental typed recovery of supported Swift relative metadata references')
args=parser.parse_args()
if args.repair_swift_relative and not args.experimental_swift:parser.error('Swift recovery requires --experimental-swift')
reference_set=args.reference_set or target_manifest[args.target]['reference_set']
reference={}
if reference_set=='fullsystem':
    reference={'REFERENCE_CACHE_PATH':project/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
        'REFERENCE_LIBRARY_ROOT':project/'runtime/fullsystem-libraries'}
ns=runpy.run_path(str(project/'scripts/dsc-image.py'),init_globals=reference)
read,pointer,uleb=ns['read'],ns['pointer'],ns['uleb']
image_config=target_manifest[args.target]
image_path,expected_hash=image_config['path'],image_config['sha256']
build=project/('runtime/rebuilt-'+args.target)
build.mkdir(parents=True,exist_ok=True)
source=ns['cache']['library_root']/image_path.lstrip('/')
data=source.read_bytes()
if hashlib.sha256(data).hexdigest()!=expected_hash:
    raise SystemExit('Unexpected reference image; review reconstruction before using another version')
modern_adapter=args.modern_adapter
assert data[:4]==b'\xcf\xfa\xed\xfe'
obj=ns['image'](image_path)
commands=[];segments=[];symbols=[];data_in_code=[];original_sections=[]
cursor=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    cmd,size=struct.unpack_from('<II',data,cursor)
    raw=bytearray(data[cursor:cursor+size])
    if cmd==0xd and 'standalone_install_name' in image_config:
        name=image_config['standalone_install_name'].encode()+b'\0'
        length=(24+len(name)+7)&~7
        raw=raw[:24]+name.ljust(length-24,b'\0')
        struct.pack_into('<I',raw,4,length)
    if cmd==0x19:
        name=raw[8:24].split(b'\0')[0].decode()
        addr,length,off,filesize=struct.unpack_from('<QQQQ',raw,24)
        sections=[]
        for i in range(struct.unpack_from('<I',raw,64)[0]):
            section=bytearray(raw[72+i*80:152+i*80])
            section_name=section[:16].split(b'\0')[0].decode()
            if section_name=='__swift5_types' and not args.experimental_swift:
                raise ValueError('Unsupported Swift image metadata')
            if section_name=='__objc_classlist' and not image_config['objc_classes']:raise ValueError('Unsupported image metadata')
            sections.append(section)
            original_sections.append((name,section_name,struct.unpack_from('<Q',section,32)[0]))
        if name!='__LINKEDIT':
            page=addr&~4095
            content=bytearray((addr+length-page+4095)&~4095)
            content[addr-page:addr-page+filesize]=data[off:off+filesize]
            segments.append({'name':name,'base':page,'content':content,'raw':raw,
                             'sections':sections,'original_start':addr,'original_size':length})
        else:linkedit_command=raw;linkedit_address=addr
    elif cmd==2:
        symtab_command=raw
        symoff,nsyms,stroff,strsize=struct.unpack_from('<IIII',raw,8)
        symbol_data=bytearray(data[symoff:symoff+16*nsyms])
        string_data=data[stroff:stroff+strsize]
        for i in range(nsyms):
            start,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,symoff+16*i)
            name=data[stroff+start:data.index(0,stroff+start)].decode()
            symbols.append((name,kind,desc,value))
    elif cmd==0xb:
        dysymtab_command=raw
        indirect_off,indirect_count=struct.unpack_from('<II',raw,56)
        indirect_data=data[indirect_off:indirect_off+4*indirect_count]
    elif cmd==0x29:
        off,length=struct.unpack_from('<II',raw,8)
        data_in_code=list(struct.iter_unpack('<IHH',data[off:off+length]))
    elif cmd not in (0xb,0x1b,0x26,0x1d,0x80000034,0x80000033,0x22,0x80000022):
        commands.append(raw)
    cursor+=size

# Some cache images split writable data and CTF metadata inside one VM page.
# A standalone loader cannot map that page as two overlapping segments. For
# explicitly reviewed pairs, preserve every original address/byte/protection
# in one page range. Section provenance is recorded; no CTF data is dropped.
coalesced_segments=[];section_segment_aliases={}
for names in image_config.get('coalesce_page_segments',[]):
    assert len(names)==2 and names==['__DATA','__CTF']
    first,second=[next(s for s in segments if s['name']==name) for name in names]
    a,b=first['base'],second['base']
    assert a<=b<a+len(first['content'])
    assert first['original_start']+first['original_size']==second['original_start']
    assert struct.unpack_from('<II',first['raw'],56)==struct.unpack_from('<II',second['raw'],56)==(3,3)
    first_flags=struct.unpack_from('<I',first['raw'],68)[0];second_flags=struct.unpack_from('<I',second['raw'],68)[0]
    assert not ((first_flags^second_flags)&~4),'Only SG_NORELOC may differ'
    merged=bytearray(max(a+len(first['content']),b+len(second['content']))-a)
    merged[:len(first['content'])]=first['content']
    start=second['original_start'];length=second['original_size']
    assert not any(merged[start-a:start-a+length]),'Original occupied bytes must not overlap'
    merged[start-a:start-a+length]=second['content'][start-b:start-b+length]
    for section in second['sections']:
        section[16:32]=first['name'].encode().ljust(16,b'\0')
        first['sections'].append(section)
    section_segment_aliases[second['name']]=first['name']
    first['content']=merged;first['original_size']=start+length-first['original_start']
    struct.pack_into('<I',first['raw'],68,first_flags&second_flags)
    segments.remove(second)
    coalesced_segments.append(dict(original_segments=names,output_segment=first['name'],
        original_addresses_preserved=True,original_payloads_preserved=True,permissions=[3,3],
        original_ctf_start=hex(start),original_ctf_size=length))

imports={}
redirected_imports=set()
literal_copies={};literal_addresses={}
coalesced_exports={};coalesced_used=set()
dependencies=list(obj.dependencies)
export_reexports=image_config.get('export_reexports',{})
for name,provider in export_reexports.items():
    if name in obj.exports or provider not in obj.dependencies:
        raise ValueError('Explicit export reexport must add a name from an original dependency')
    if ns['resolve'](provider,name) is None:
        raise ValueError('Explicit export reexport has no original provider symbol: '+name)
compat_reexports=image_config.get('compat_reexports',[])
if len(set(compat_reexports))!=len(compat_reexports):raise ValueError('Duplicate compatibility reexport')
for provider in compat_reexports:
    if not provider.startswith('/usr/lib/libDarling') or not provider.endswith('.dylib'):
        raise ValueError('Compatibility reexports must name explicit Darling adapters')
    if provider in dependencies:raise ValueError('Compatibility reexport conflicts with an original dependency')
    dependencies.append(provider)
provider_overrides=image_config.get('import_providers',{})
def dependency_ordinal(provider):
    if provider not in dependencies:
        dependencies.append(provider)
    return dependencies.index(provider)+1
modern_names={'_ccder_blob_'+name for name in ('decode_len','decode_range','decode_sequence_tl',
    'decode_tag','decode_tl','encode_body_tl','encode_tl','reserve_tl')}
modern_names|={'_malloc_type_malloc','_malloc_type_realloc','__ZnwmSt19__type_descriptor_t'}
modern_names|={'__ZnamSt19__type_descriptor_t','__ZdlPvSt19__type_descriptor_t','__ZdaPvSt19__type_descriptor_t'}
modern_names.add('_xpc_dictionary_create_empty')
modern_names.add('_kSecUseSystemKeychainAlways')
modern_names.add('_malloc_type_calloc')
for name,kind,desc,value in symbols:
    if kind&0xe==0 and kind&1:
        ordinal=desc>>8
        if not 0<=ordinal<=len(obj.dependencies):raise ValueError('Unsupported import ordinal')
        target=ns['resolve'](obj.dependencies[ordinal-1] if ordinal else image_path,name)
        if target is None:raise ValueError('Cannot resolve original import '+name)
        if modern_adapter and name in modern_names:
            ordinal=dependency_ordinal('/usr/lib/libDarlingDER.dylib');redirected_imports.add(name)
        if name in provider_overrides:
            ordinal=dependency_ordinal(provider_overrides[name]);redirected_imports.add(name)
        imports.setdefault(target,[]).append((name,ordinal,bool(desc&0x40)))
for name,provider in image_config.get('cache_imports',{}).items():
    target=ns['resolve'](provider,name)
    if target is None:raise ValueError('Unresolved cache-coalesced constant export '+name)
    destination_provider=provider_overrides.get(name,provider)
    if destination_provider!=provider:redirected_imports.add(name)
    ordinal=dependency_ordinal(destination_provider)
    imports.setdefault(target,[]).append((name,ordinal,False))
for provider in image_config.get('recover_coalesced_data_exports',[]):
    if not args.experimental_swift:raise ValueError('Coalesced Swift-data recovery is experimental')
    provider_image=ns['image'](provider)
    ordinal=dependency_ordinal(provider)
    for name,value in sorted(provider_image.exports.items(),key=lambda item:(len(item[0]),item[0])):
        if not name.startswith('_$s') or value[0]!='address' or value[2]!=0:continue
        target=value[1]
        # __TEXT contains both instructions and read-only metadata. Use the
        # actual section attributes so protocol descriptors and requirement
        # tables are recovered without mistaking function aliases for data.
        if not any(start<=target<start+length and not flags&0x80000400
                for _,_,start,length,flags in provider_image.sections):continue
        if target in imports:continue
        imports[target]=[(name,ordinal,False)]
        coalesced_exports[target]=(name,provider)
for provider in image_config.get('recover_coalesced_function_exports',[]):
    if not args.experimental_swift:raise ValueError('Coalesced function recovery is experimental')
    provider_image=ns['image'](provider)
    ordinal=dependency_ordinal(provider)
    names_at_address={}
    for name,value in provider_image.exports.items():
        if value[0]=='address':names_at_address.setdefault(value[1],[]).append(name)
    for name,value in sorted(provider_image.exports.items(),key=lambda item:(len(item[0]),item[0])):
        if not name.startswith('_$s') or value[0]!='address' or value[2]!=0:continue
        target=value[1]
        # A folded body can have unrelated public aliases. Across runtime
        # versions those names need not remain interchangeable; require the
        # original address to identify exactly one public symbol.
        if len(names_at_address[target])!=1:continue
        if not any(start<=target<start+length and flags&0x80000400
                for _,_,start,length,flags in provider_image.sections):continue
        if target in imports:continue
        imports[target]=[(name,ordinal,False)]
        coalesced_exports[target]=(name,provider)
for name,provider in image_config.get('cache_enum_case_literals',{}).items():
    # Swift's exported enum-case index variables are four-byte literals. This
    # explicitly pinned experiment copies their actual bytes, not a guessed
    # enum value or an implementation of the provider's numerical APIs.
    if not args.experimental_swift or not name.endswith('mFWC'):
        raise ValueError('Enum-case literal copying is restricted to the Swift experiment')
    target=ns['resolve'](provider,name)
    if target is None:raise ValueError('Unresolved enum-case literal export '+name)
    payload=read(target,4)
    if struct.unpack('<I',payload)[0]>65535:raise ValueError('Unexpected enum-case index representation')
    literal_copies[target]=payload
for name,record in image_config.get('cache_u32_constants',{}).items():
    target=ns['resolve'](record['provider'],name)
    if target is None:raise ValueError('Cannot resolve pinned uint32 constant '+name)
    payload=read(target,4)
    if payload!=bytes.fromhex(record['bytes']):raise ValueError('Pinned uint32 constant changed: '+name)
    literal_copies[target]=payload
call_overrides=image_config.get('backend_call_overrides',[])
for record in call_overrides:dependency_ordinal(record['provider'])
for provider in dependencies[len(obj.dependencies):]:
    name=provider.encode()+b'\0'
    size=(24+len(name)+7)&~7
    command=0x8000001f if provider in compat_reexports else 0xc
    commands.append(bytearray(struct.pack('<6I',command,size,24,0,0x10000,0x10000)+name.ljust(size-24,b'\0')))

original_base=obj.base
header_capacity=min(struct.unpack_from('<Q',section,32)[0] for s in segments
    if s['name']=='__TEXT' for section in s['sections'])-original_base
lazy_ranges=[];stub_ranges=[]
for s in segments:
    for section in s['sections']:
        if section[:16].split(b'\0')[0]==b'__la_symbol_ptr':
            start,size=struct.unpack_from('<QQ',section,32);lazy_ranges.append((start,start+size))
        if struct.unpack_from('<I',section,64)[0]&255==8:
            start,size=struct.unpack_from('<QQ',section,32)
            entry_size=struct.unpack_from('<I',section,72)[0]
            if entry_size!=6:raise ValueError('Unsupported x86_64 symbol stub size')
            stub_ranges.append((start,start+size))
helper_segment=next(s for s in segments if s['name']=='__TEXT')
helper_base=helper_segment['base']+len(helper_segment['content'])
lazy_capacity=sum((b-a)//8 for a,b in lazy_ranges)+sum((b-a)//6 for a,b in stub_ranges)
helper_capacity=((15+10*lazy_capacity+4095)&~4095) if args.lazy_functions and lazy_capacity else 0
if helper_capacity:
    helper_segment['content'].extend(bytes(helper_capacity))
    # Executable helper bytes are mapped by __TEXT regardless of whether a
    # separate section describes them. Tiny cache images can lack room for
    # another section command. Keep this choice explicit in the pinned layout.
    if image_config.get('describe_lazy_helpers',True):
        section=bytearray(struct.pack('<16s16sQQIIIIIIII',b'__lazy_helper',b'__TEXT',
            helper_base,helper_capacity,0,0,0,0,0x80000400,0,0,0))
        helper_segment['sections'].append(section)
call_code_base=helper_segment['base']+len(helper_segment['content'])
if call_overrides:helper_segment['content'].extend(bytes((6*len(call_overrides)+4095)&~4095))
proxy_base=helper_segment['base']+len(helper_segment['content'])
proxy={'name':'__COMPAT','base':proxy_base,'content':bytearray(),'sections':[],
       'raw':bytearray(struct.pack('<II16sQQQQiiII',0x19,72,b'__COMPAT',proxy_base,0,0,0,3,3,0,0)),
       'original_start':proxy_base,'original_size':0}
segments.append(proxy)
rebases={};binds={};lazy_binds={};external_slots={};strings={}
tagged_string_rebases=[]

def own(address):
    return any(s['original_start']<=address<s['original_start']+s['original_size']
               for s in segments if s is not proxy)

def allocate(payload,alignment=8):
    buf=proxy['content']
    buf.extend(b'\0'*(-len(buf)%alignment))
    address=proxy_base+len(buf)
    buf.extend(payload)
    return address

def store(address,value):
    for segment in segments:
        offset=address-segment['base']
        if 0<=offset<=len(segment['content'])-8:
            struct.pack_into('<Q',segment['content'],offset,value);return
    raise ValueError(f'Write outside reconstructed image {address:#x}')

def classify(slot,target,selector=False,lazy_stub=False):
    if not target:store(slot,0);return
    if args.repair_swift_relative and target>>60==8 and own(slot-8):
        # Swift 6.3.3 StringObject.swift: large immortal native literals have
        # discriminator 0x8 and a UTF-8 pointer biased by nativeBias (32).
        # Accept only canonical literal flags and validated local UTF-8 bytes.
        address=target&0x0fffffffffffffff
        count_flags=struct.unpack('<Q',read(slot-8,8))[0]
        count=count_flags&0x0000ffffffffffff
        flags=count_flags&0xffff000000000000
        if flags in (0xd000000000000000,0x1000000000000000) and 16<=count<=1048576 and own(address) and own(address+32+count):
            payload=read(address+32,count+1)
            if payload[-1]!=0:raise ValueError('Swift immortal literal has no trailing NUL')
            payload[:-1].decode('utf-8')
            if flags==0xd000000000000000 and not payload[:-1].isascii():
                raise ValueError('Swift immortal literal violates its ASCII flag')
            store(slot,target);rebases[slot]=target
            tagged_string_rebases.append({'slot':hex(slot),'utf8_length':count,
                'payload_sha256':hashlib.sha256(payload[:-1]).hexdigest()})
            return
    if own(target):
        store(slot,target);rebases[slot]=target;return
    if target in literal_copies:
        if target not in literal_addresses:literal_addresses[target]=allocate(literal_copies[target],4)
        address=literal_addresses[target]
        store(slot,address);rebases[slot]=address;return
    candidates=imports.get(target)
    if candidates:
        if target in coalesced_exports:coalesced_used.add(coalesced_exports[target])
        destination=lazy_binds if args.lazy_functions and (lazy_stub or any(a<=slot<b for a,b in lazy_ranges)) else binds
        destination[slot]=(*candidates[0],0);store(slot,0);return
    if selector:
        payload=read(target,1024).split(b'\0')[0]
        if not payload or any(c<32 or c>=127 for c in payload):raise ValueError('Invalid selector string')
        if payload not in strings:strings[payload]=allocate(payload+b'\0',1)
        store(slot,strings[payload]);rebases[slot]=strings[payload];return
    for exported,candidates in imports.items():
        # objc4/runtime/objc-exception.mm explicitly stores
        # objc_ehtype_vtable+2 in objc_typeinfo::vtable (two 8-byte words on
        # x86_64). Bind the real runtime's table with that exact ABI addend.
        if target-exported==16 and candidates[0][0]=='_objc_ehtype_vtable':
            binds[slot]=(*candidates[0],16);store(slot,0);return
        if 0<target-exported<=64 and candidates[0][0].startswith('__ZTV'):
            binds[slot]=(*candidates[0],target-exported);store(slot,0);return
    raise ValueError(f'Unclassified cache pointer at {slot:#x} -> {target:#x}')

selector_ranges=[]
for s in segments:
    if s['name']=='__TEXT' and args.experimental_swift:
        # Merge only the initial code/literal prefix. Swift discovery sections
        # must keep their real names and must not overlap the merged __text.
        text_section=next(section for section in s['sections'] if section[:16].split(b'\0')[0]==b'__text')
        start=struct.unpack_from('<Q',text_section,32)[0]
        retained=lambda name:name.startswith(b'__swift5_') or name in (
            b'__unwind_info',b'__eh_frame',b'__objc_classname',b'__objc_methname',b'__objc_methtype',b'__lazy_helper')
        boundary=min(struct.unpack_from('<Q',section,32)[0] for section in s['sections']
            if retained(section[:16].split(b'\0')[0]) and struct.unpack_from('<Q',section,32)[0]>start)
        struct.pack_into('<Q',text_section,40,boundary-start)
        s['sections']=[text_section,*[section for section in s['sections']
            if struct.unpack_from('<Q',section,32)[0]>=boundary]]
    if s['name']=='__TEXT' and not args.experimental_swift and any(
            struct.unpack_from('<I',section,64)[0]&0x80000400 and struct.unpack_from('<Q',section,40)[0]
            for section in s['sections']):
        # Keep the unwind/Objective-C sections discoverable, while combining
        # code, stubs and read-only literals to make room for load commands.
        text_section=next(section for section in s['sections'] if section[:16].split(b'\0')[0]==b'__text')
        unwind=next(section for section in s['sections'] if section[:16].split(b'\0')[0]==b'__unwind_info')
        start=struct.unpack_from('<Q',text_section,32)[0]
        struct.pack_into('<Q',text_section,40,struct.unpack_from('<Q',unwind,32)[0]-start)
        s['sections']=[text_section,unwind,*[section for section in s['sections']
            if section[:16].split(b'\0')[0] in (b'__objc_classname',b'__objc_methname',b'__objc_methtype',b'__lazy_helper')
            or (args.experimental_swift and section[:16].split(b'\0')[0].startswith(b'__swift5_'))]]
    for section in s['sections']:
        if section[:16].split(b'\0')[0]==b'__objc_selrefs':
            start,size=struct.unpack_from('<QQ',section,32)
            selector_ranges.append((start,start+size))

def cache_slots(start,end):
    # Walk the real v2 page chains, not an arbitrary scan for pointer-like data.
    for ctx,mapping,info in ns['cache']['mappings']:
        if info is None or end<=mapping.address or start>=mapping.address+mapping.size:continue
        shift=(info.delta_mask&-info.delta_mask).bit_length()-3
        first=max(0,(start-mapping.address)//info.page_size)
        last=min(info.page_starts_count,(end-mapping.address+info.page_size-1)//info.page_size)
        for page in range(first,last):
            entry=struct.unpack_from('<H',ctx.file,info._fileOff_+info.page_starts_offset+2*page)[0]
            if entry&0x4000:continue
            offsets=[]
            if entry&0x8000:
                extra=entry&0x3fff
                while True:
                    value=struct.unpack_from('<H',ctx.file,info._fileOff_+info.page_extras_offset+2*extra)[0]
                    offsets.append((value&0x3fff)*4);extra+=1
                    if value&0x8000:break
            else:offsets=[entry*4]
            for offset in offsets:
                while True:
                    if not 0<=offset<=info.page_size-8:raise ValueError('Invalid cache chain extent')
                    address=mapping.address+page*info.page_size+offset
                    raw=struct.unpack('<Q',read(address,8))[0]
                    if start<=address<end:yield address
                    delta=(raw&info.delta_mask)>>shift
                    if not delta:break
                    offset+=delta

custom_slots=set();objc_report=None
restore_objc_metadata=bool(image_config['objc_classes'] or image_config.get('restore_objc_protocols',False)
                           or image_config.get('restore_objc_categories',False))
if image_config.get('restore_objc_categories',False) and not any(
        name=='__objc_catlist' for _,name,_ in original_sections):
    raise ValueError('Category restoration requires an original category-list section')
if image_config.get('restore_objc_protocols',False) and not any(
        name=='__objc_protolist' for _,name,_ in original_sections):
    raise ValueError('Protocol restoration requires an original protocol-list section')
if not restore_objc_metadata:
    # Selector-only C/ObjC facades also carry cache preoptimization flags.
    # Their copied selector strings must be interned by the actual runtime.
    for segment in segments:
        for section in segment['sections']:
            if section[:16].split(b'\0')[0]!=b'__objc_imageinfo':continue
            address,length=struct.unpack_from('<QQ',section,32)
            if length!=8:raise ValueError('Unexpected Objective-C image-info size')
            original_flags=struct.unpack('<I',read(address+4,4))[0]
            struct.pack_into('<I',segment['content'],address+4-segment['base'],original_flags&~(1|8|16|128))
if restore_objc_metadata:
    restore=runpy.run_path(str(project/'scripts/restore-objc-metadata.py'))['restore']
    objc_ordinal=obj.dependencies.index('/usr/lib/libobjc.A.dylib')+1
    expected_classes=image_config['objc_classes']
    custom_slots,objc_report=restore(segments,ns,allocate,store,classify,binds,rebases,own,objc_ordinal,project,expected_classes)
    if 'objc_registration_classes' in image_config:
        allowed=set(image_config['objc_registration_classes'])
        if len(allowed)!=len(image_config['objc_registration_classes']):raise ValueError('Duplicate class registration whitelist')
        found=set();removed=[]
        for segment in segments:
            for section in segment['sections']:
                section_name=section[:16].split(b'\0')[0]
                address,length=struct.unpack_from('<QQ',section,32)
                if section_name not in (b'__objc_classlist',b'__objc_nlclslist'):continue
                kept=[]
                for offset in range(0,length,8):
                    target=pointer(address+offset);ro=pointer(target+32)&~7
                    name=read(pointer(ro+24),512).split(b'\0')[0].decode()
                    if name in allowed:
                        kept.append(target)
                        if section_name==b'__objc_classlist':found.add(name)
                    else:removed.append(name)
                for offset in range(0,length,8):
                    slot=address+offset
                    if offset//8<len(kept):
                        target=kept[offset//8];store(slot,target);rebases[slot]=target
                    else:store(slot,0);rebases.pop(slot,None)
                    custom_slots.add(slot)
                struct.pack_into('<Q',section,40,8*len(kept))
        if found!=allowed:raise ValueError('Registration whitelist does not match the original class definitions')
        objc_report['registered_classes']=sorted(found)
        objc_report['classes_not_registered']=sorted(set(removed))
tls_restore=runpy.run_path(str(project/'scripts/restore-tls-metadata.py'))['restore']
tls_slots,tls_report=tls_restore(segments,ns,store,binds,obj)
custom_slots.update(tls_slots)
swift_report=None
if args.repair_swift_relative:
    # Swift IRGen deliberately puts binary generic environments alongside
    # mangled strings in __swift5_typeref. Recover them from authoritative
    # local symbols instead of interpreting their integer headers as strings.
    ns['swift_generic_environments']=[value for name,kind,_,value in symbols
        if kind&0xe==0xe and name.startswith('_generic environment ')]
    swift_restore=runpy.run_path(str(project/'scripts/restore-swift-metadata.py'))['restore']
    swift_report=swift_restore(segments,ns,allocate,store,classify,own)
    if swift_report['resilient_objc_metaclasses'] or swift_report['resilient_objc_class_ro']:
        restore=runpy.run_path(str(project/'scripts/restore-objc-metadata.py'))['restore']
        extra_slots,extra_report=restore(segments,ns,allocate,store,classify,binds,rebases,own,
            obj.dependencies.index('/usr/lib/libobjc.A.dylib')+1,project,image_config['objc_classes'],
            swift_report['resilient_objc_metaclasses'],swift_report['resilient_objc_class_ro'],True)
        custom_slots.update(extra_slots)
        if objc_report is None:objc_report=extra_report
        else:objc_report['swift_resilient_metadata']=extra_report
for s in list(segments):
    if s is proxy:continue
    for slot in cache_slots(s['original_start'],s['original_start']+s['original_size']):
        if slot in custom_slots:continue
        classify(slot,pointer(slot),any(a<=slot<b for a,b in selector_ranges))

# LLVM needs authoritative function boundaries when local symbols were
# stripped. The experimental Swift path also recognizes only strictly checked
# tail jump tables; unsupported tables still cause reconstruction to fail.
code_analysis=None
if args.experimental_swift or args.analyze_code:
    analysis=runpy.run_path(str(project/'scripts/cache-code-analysis.py'))
    analysis_source=build/(Path(image_path).name+'.analysis-only.macho')
    functions=analysis['reference_with_function_labels'](source,analysis_source)
    disassembly=subprocess.check_output(['llvm-objdump-19','-d',str(analysis_source)],text=True)
    inferred_tables=analysis['tail_jump_tables'](disassembly,functions,read)
    code_analysis={'function_entries':len(functions),'tail_tables':inferred_tables,
        'analysis_copy_is_not_runnable_or_installed':True}
    if image_config.get('code_constant_ranges'):
        code_analysis['constant_ranges']=analysis['validated_constant_ranges'](
            disassembly,image_config['code_constant_ranges'],original_base,read)
    if image_config.get('source_assembly_literals'):
        literal_analysis=runpy.run_path(str(project/'scripts/source-assembly-literals.py'))
        code_analysis['source_assembly_literals']=literal_analysis['validate'](
            disassembly,image_config['source_assembly_literals'],original_base,read,functions,source,project)
    (build/'code-analysis.json').write_text(json.dumps(code_analysis,indent=2)+'\n')
else:
    disassembly=subprocess.check_output(['llvm-objdump-19','-d',str(source)],text=True)
(build/'original-disassembly.log').write_text(disassembly)

# Skip data before rewriting or rejecting anything resembling an instruction.
data_ranges=[]
all_code_data=list(data_in_code)
if code_analysis:
    all_code_data.extend((table['start']-original_base,table['end']-table['start'],0)
        for table in code_analysis['tail_tables'])
    all_code_data.extend((record['start']-original_base,record['end']-record['start'],0)
        for record in code_analysis.get('constant_ranges',[]))
    all_code_data.extend((record['start']-original_base,record['end']-record['start'],0)
        for record in code_analysis.get('source_assembly_literals',[]))
for off,size,_ in sorted(all_code_data):
    if not size:continue
    start,end=original_base+off,original_base+off+size
    if data_ranges and start<=data_ranges[-1][1]:data_ranges[-1]=(data_ranges[-1][0],max(data_ranges[-1][1],end))
    else:data_ranges.append((start,end))
data_starts=[start for start,end in data_ranges]
def in_code_data(address):
    index=bisect_right(data_starts,address)-1
    return index>=0 and address<data_ranges[index][1]
def rip_target(address,encoded,operand):
    ref=re.search(r'## (0x[0-9a-f]+)',operand)
    if ref:return int(ref[1],16)
    displacement=re.search(r'(-?(?:0x[0-9a-f]+|\d+))?\(%rip\)',operand)
    if not displacement:raise ValueError('RIP instruction missing its target')
    return address+len(encoded)+int(displacement[1] or '0',0)

def symbol_stub(address,encoded):
    return encoded[:2]==b'\xff\x25' and len(encoded)==6 and any(a<=address<b for a,b in stub_ranges)

# A pooled slot used to take a function's address (e.g. a weak availability
# check) must remain eager, even if a symbol stub also calls through it.
non_stub_refs=set()
for line in disassembly.splitlines():
    match=re.match(r'^([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)',line)
    if not match or '(%rip)' not in match[3]:continue
    address=int(match[1],16);encoded=bytes.fromhex(match[2])
    if in_code_data(address):continue
    if not symbol_stub(address,encoded):non_stub_refs.add(rip_target(address,encoded,match[3]))
patched=[]
override_sites={original_base+int(record['instruction_offset'],0):(index,record)
    for index,record in enumerate(call_overrides)}
if len(override_sites)!=len(call_overrides):raise ValueError('Duplicate backend call override')
applied_overrides=[]
unclassified_code_slots={}
unsupported_code=[]
for line in disassembly.splitlines():
    match=re.match(r'^([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)',line)
    if not match:continue
    address=int(match[1],16)
    if in_code_data(address):continue
    encoded=bytes.fromhex(match[2])
    operand=match[3]
    if address in override_sites:
        index,record=override_sites[address]
        if encoded!=bytes.fromhex(record['instruction_bytes']) or len(encoded)!=5 or encoded[0]!=0xe9:
            raise ValueError('Backend override must match its pinned direct tail jump')
        target=address+5+struct.unpack('<i',encoded[1:])[0]
        stub=read(target,6)
        if not symbol_stub(target,stub):raise ValueError('Backend tail jump does not enter a canonical original symbol stub')
        original_slot=target+6+struct.unpack('<i',stub[2:])[0]
        if record['original_symbol'] not in [name for name,_,_ in imports.get(pointer(original_slot),[])]:
            raise ValueError('Backend override original callee does not match')
        slot=allocate(bytes(8));binds[slot]=(record['symbol'],dependencies.index(record['provider'])+1,False,0)
        thunk=call_code_base+6*index
        at=thunk-helper_segment['base']
        helper_segment['content'][at:at+6]=b'\xff\x25'+struct.pack('<i',slot-thunk-6)
        segment=next(s for s in segments if s['original_start']<=address<s['original_start']+s['original_size'])
        at=address-segment['base']
        segment['content'][at:at+5]=b'\xe9'+struct.pack('<i',thunk-address-5)
        applied_overrides.append({'instruction':hex(address),'symbol':record['symbol'],
            'original_symbol':record['original_symbol'],'provider':record['provider']})
        continue
    direct=re.search(r'\b(?:callq?|jmpq?|j\w+)\s+(0x[0-9a-f]+)',operand)
    if direct and not own(int(direct[1],16)):
        unsupported_code.append({'instruction':line,'error':'Unreconstructed direct cache branch'})
        continue
    absolute=re.search(r'\bmovabsq\s+\$(0x[0-9a-f]+)',operand)
    if absolute:
        try:ns['cache']['locate'](int(absolute[1],16))
        except ValueError:pass
        else:
            unsupported_code.append({'instruction':line,'error':'Unreconstructed absolute cache address'})
            continue
    if '(%rip)' not in operand:continue
    target=rip_target(address,encoded,operand)
    if own(target):continue
    if re.search(r'\bleaq?\b',operand):
        # Clang can select between addresses of ObjC class-reference cells,
        # then load the selected Class. The cache coalesces those cells too.
        # Recreate the cell, preserving LEA's pointer-to-pointer semantics.
        # Do not mistake a constant object's isa for a class-reference cell.
        value=pointer(target)
        candidates=imports.get(value,[])
        class_names=[name.removeprefix('_OBJC_CLASS_$_') for name,_,_ in candidates
            if name.startswith('_OBJC_CLASS_$_')]
        if not class_names or any(name.startswith(('NSConstant','__NSCF')) or name=='Protocol' for name in class_names):
            unsupported_code.append({'instruction':line,'error':'External address-taking needs a separate data reconstruction'})
            continue
    if target not in external_slots:
        if target in unclassified_code_slots:continue
        slot=allocate(bytes(8))
        # Cache optimization moves a symbol stub's pointer into a pooled GOT.
        # Only the canonical six-byte indirect jump inside S_SYMBOL_STUBS is
        # eligible for lazy restoration; ordinary data/GOT references stay eager.
        is_stub=symbol_stub(address,encoded) and target not in non_stub_refs
        try:classify(slot,pointer(target),lazy_stub=is_stub)
        except ValueError as error:
            try:unresolved_value=hex(pointer(target))
            except ValueError:unresolved_value=None
            unclassified_code_slots[target]={'instruction':line,'slot':hex(target),
                'value':unresolved_value,'error':str(error)}
            continue
        external_slots[target]=slot
    replacement=external_slots[target]-(address+len(encoded))
    old=struct.pack('<i',target-(address+len(encoded)))
    locations=[i for i in range(len(encoded)-3) if encoded[i:i+4]==old]
    if len(locations)!=1:raise ValueError('Ambiguous RIP displacement patch')
    segment=next(s for s in segments if s['base']<=address<s['base']+len(s['content']))
    off=address-segment['base']+locations[0]
    struct.pack_into('<i',segment['content'],off,replacement)
    patched.append({'instruction':hex(address),'original_slot':hex(target),'new_slot':hex(external_slots[target])})

diagnostic=build/'unclassified-code-imports.json'
if len(applied_overrides)!=len(call_overrides):raise ValueError('Not every pinned backend tail jump was restored')
diagnostic.write_text(json.dumps(list(unclassified_code_slots.values()),indent=2)+'\n')
(build/'unsupported-code.json').write_text(json.dumps(unsupported_code,indent=2)+'\n')
if unclassified_code_slots or unsupported_code:
    first=next(iter(unclassified_code_slots.values())) if unclassified_code_slots else unsupported_code[0]
    raise ValueError(f"{len(unclassified_code_slots)} unresolved code import slots; no library emitted. "
        f"{len(unsupported_code)} unsupported instructions. See {diagnostic}. "
        f"First: {first['instruction']}: {first['error']}")

if lazy_binds:
    private_slot=allocate(bytes(8));binder_slot=allocate(bytes(8))
    binder_provider=next((p for p in ('/usr/lib/libSystem.B.dylib','/usr/lib/system/libdyld.dylib')
        if p in dependencies),None)
    if binder_provider is None:raise ValueError('No dyld_stub_binder provider dependency')
    system_ordinal=dependencies.index(binder_provider)+1
    binds[binder_slot]=('dyld_stub_binder',system_ordinal,False,0)
    # Standard x86_64 Mach-O stub-helper ABI: push &__dyld_private, then
    # tail-jump through dyld_stub_binder. Per-symbol helpers push stream offsets.
    helper_offset=helper_base-helper_segment['base']
    common=(b'\x4c\x8d\x1d'+struct.pack('<i',private_slot-helper_base-7)+
            b'\x41\x53\xff\x25'+struct.pack('<i',binder_slot-helper_base-15))
    helper_segment['content'][helper_offset:helper_offset+15]=common

proxy['content'].extend(b'\0'*(-len(proxy['content'])%4096))
proxy_section=bytearray(struct.pack('<16s16sQQIIIIIIII',b'__data',b'__COMPAT',
    proxy_base,len(proxy['content']),0,3,0,0,0,0,0,0))
proxy['sections']=[proxy_section] if image_config.get('describe_compat_data',True) else []
if not proxy['content']:segments.remove(proxy)
segments.sort(key=lambda s:s['base'])
assert segments[0]['name']=='__TEXT'
for s in segments:
    leading=s['original_start']-s['base']
    if leading and not image_config.get('describe_leading_padding',True):
        # These bytes are newly allocated zero page-alignment padding, not
        # original image data. A tight header can omit their section record,
        # but no dyld fixup may then refer to that undescribed range.
        if any(s['base']<=address<s['original_start'] for address in (*rebases,*binds,*lazy_binds)):
            raise ValueError('Cannot omit leading-padding section containing a fixup')
    if leading and image_config.get('describe_leading_padding',True):
        padding=bytearray(struct.pack('<16s16sQQIIIIIIII',b'__padding',s['name'].encode(),
            s['base'],leading,0,0,0,0,0,0,0,0))
        s['sections'].insert(0,padding)
    s['raw']=s['raw'][:72]+b''.join(s['sections'])
    struct.pack_into('<I',s['raw'],4,len(s['raw']))
    struct.pack_into('<I',s['raw'],64,len(s['sections']))

def position(address):
    for index,s in enumerate(segments):
        if s['base']<=address<s['base']+len(s['content']):return index,address-s['base']
    raise ValueError('Unmapped fixup address')

def sleb(value):
    result=bytearray()
    while True:
        byte=value&127;value>>=7
        done=(value==0 and not byte&64) or (value==-1 and bool(byte&64))
        result.append(byte if done else byte|128)
        if done:return bytes(result)

lazy_bytes=bytearray()
for index,(address,(name,ordinal,weak,addend)) in enumerate(sorted(lazy_binds.items())):
    segment_index,offset=position(address)
    stream_offset=len(lazy_bytes)
    lazy_bytes+=(b'\x30' if ordinal==0 else bytes([0x10|ordinal])) if ordinal<=15 else b'\x20'+uleb(ordinal)
    # dyld's fast lazy binder accepts only zero-addend pointer bindings and
    # rejects SET_ADDEND_SLEB even when its operand is zero.
    if addend:raise ValueError('Lazy binding with a nonzero addend is unsupported')
    lazy_bytes+=bytes([0x40|int(weak)])+name.encode()+b'\0\x51'
    lazy_bytes+=bytes([0x70|segment_index])+uleb(offset)+b'\x90\0'
    entry=helper_base+15+index*10
    if entry+10>helper_base+helper_capacity:raise ValueError('Lazy helper area overflow')
    payload=b'\x68'+struct.pack('<I',stream_offset)+b'\xe9'+struct.pack('<i',helper_base-entry-10)
    at=entry-helper_segment['base']
    helper_segment['content'][at:at+10]=payload
    store(address,entry);rebases[address]=entry

rebase_bytes=bytearray(b'\x11')
for address in sorted(rebases):
    index,offset=position(address)
    rebase_bytes+=bytes([0x20|index])+uleb(offset)+b'\x51'
rebase_bytes+=b'\0'

bind_bytes=bytearray()
for address,(name,ordinal,weak,addend) in sorted(binds.items()):
    index,offset=position(address)
    bind_bytes+=(b'\x30' if ordinal==0 else bytes([0x10|ordinal])) if ordinal<=15 else b'\x20'+uleb(ordinal)
    bind_bytes+=bytes([0x40|int(weak)])+name.encode()+b'\0\x51\x60'+sleb(addend)
    bind_bytes+=bytes([0x70|index])+uleb(offset)+b'\x90'
bind_bytes+=b'\0'

exports={};function_resolvers=[]
for name,provider in export_reexports.items():
    exports[name.encode()]=uleb(8)+uleb(dependencies.index(provider)+1)+name.encode()+b'\0'
for name,value in obj.exports.items():
    if value[0]=='reexport':
        exports[name.encode()]=uleb(8)+uleb(value[1])+value[2].encode()+b'\0'
        continue
    if value[0]!='address' or value[2]&~(1|4|0x10):raise ValueError('Unsupported export type')
    if value[2]&1:
        # A thread-local export names a restored on-disk TLV descriptor, not
        # the process-wide storage of the variable. Preserve dyld's kind bit.
        if value[2]&0x10 or not tls_report or not any(
                flags&255==0x13 and start<=value[1]<start+length and (value[1]-start)%24==0
                for _,_,start,length,flags in obj.sections):
            raise ValueError('Thread-local export lacks a restored TLV descriptor: '+name)
    payload=uleb(value[2])+uleb(value[1]-original_base)
    if value[2]&0x10:
        # Classic x86_64 dyld EXPORT_SYMBOL_FLAGS_STUB_AND_RESOLVER stores
        # both a public stub and an image-relative resolver entry. Retain the
        # original CPU-selection routine; do not freeze a cached CPU choice.
        if len(value)!=4 or not own(value[1]) or not own(value[3]):
            raise ValueError('Function resolver must remain in its original image: '+name)
        if not all(any(start<=address<start+length and flags&0x80000400
                for _,_,start,length,flags in obj.sections) for address in (value[1],value[3])):
            raise ValueError('Function resolver/stub is outside original executable sections: '+name)
        payload+=uleb(value[3]-original_base)
        function_resolvers.append({'symbol':name,'stub':hex(value[1]),'resolver':hex(value[3])})
    exports[name.encode()]=payload
nodes=[]
def make_node(items,prefix):
    node={'terminal':exports.get(prefix,b''),'children':[],'offset':0};nodes.append(node)
    remaining=[n for n in items if n!=prefix]
    for first in sorted({n[len(prefix)] for n in remaining}):
        group=[n for n in remaining if n[len(prefix)]==first]
        common=group[0]
        for name in group[1:]:
            i=len(prefix)
            while i<min(len(common),len(name)) and common[i]==name[i]:i+=1
            common=common[:i]
        node['children'].append((common[len(prefix):],make_node(group,common)))
    return node
make_node(list(exports),b'')
def encode_node(node):
    return (uleb(len(node['terminal']))+node['terminal']+bytes([len(node['children'])])+
            b''.join(edge+b'\0'+uleb(child['offset']) for edge,child in node['children']))
for _ in range(100):
    cursor=0;changed=False
    for node in nodes:
        changed|=node['offset']!=cursor;node['offset']=cursor;cursor+=len(encode_node(node))
    if not changed:break
else:raise ValueError('Export trie did not converge')
export_bytes=b''.join(encode_node(node) for node in nodes)

output=bytearray()
segment_commands=[]
# Standalone dylibs use a zero preferred base, as Darling's normal libraries
# do. Every cache pointer identified above is now image-relative; classic
# dyld rebasing must restore it at the actual dynamically chosen load address.
for address,target in rebases.items():store(address,target-original_base)
for s in segments:
    fileoff=len(output)
    raw=s['raw']
    struct.pack_into('<QQQQ',raw,24,s['base']-original_base,len(s['content']),fileoff,len(s['content']))
    for i,section in enumerate(s['sections']):
        section_address=struct.unpack_from('<Q',section,32)[0]
        normalized_section=bytearray(section)
        flags=struct.unpack_from('<I',normalized_section,64)[0]
        struct.pack_into('<I',normalized_section,48,0 if flags&255 in (1,0xc,0x12) else fileoff+section_address-s['base'])
        struct.pack_into('<Q',normalized_section,32,section_address-original_base)
        raw[72+80*i:152+80*i]=normalized_section
    segment_commands.append(raw)
    output+=s['content']
linkoff=len(output)
streams=[]
for payload in (rebase_bytes,bind_bytes,b'',lazy_bytes,export_bytes):
    streams.extend([len(output) if payload else 0,len(payload)])
    output+=payload
new_section_indices={}
section_index=0
for s in segments:
    for section in s['sections']:
        section_index+=1
        name=section[:16].split(b'\0')[0].decode()
        addr=struct.unpack_from('<Q',section,32)[0]
        new_section_indices[(s['name'],name,addr)]=section_index
for i in range(nsyms):
    kind,old_section=struct.unpack_from('<BB',symbol_data,16*i+4)
    name,_,desc,_=symbols[i]
    if kind&0xe==0 and kind&1 and name in redirected_imports:
        provider=provider_overrides.get(name,'/usr/lib/libDarlingDER.dylib')
        struct.pack_into('<H',symbol_data,16*i+6,(desc&255)|(dependencies.index(provider)+1)<<8)
    if kind&0xe==0xe and old_section:
        old_key=original_sections[old_section-1]
        old_key=(section_segment_aliases.get(old_key[0],old_key[0]),*old_key[1:])
        if old_key in new_section_indices:
            new_index=new_section_indices[old_key]
        else:
            value=struct.unpack_from('<Q',symbol_data,16*i+8)[0]
            matches=[index for (segment_name,name,addr),index in new_section_indices.items()
                if segment_name==old_key[0] and any(
                    struct.unpack_from('<Q',section,32)[0]<=value<sum(struct.unpack_from('<QQ',section,32))
                    for s in segments if s['name']==segment_name for section in s['sections']
                    if section[:16].split(b'\0')[0].decode()==name)]
            if len(matches)!=1:raise ValueError('Cannot place retained symbol in new section')
            new_index=matches[0]
        symbol_data[16*i+5]=new_index
        value=struct.unpack_from('<Q',symbol_data,16*i+8)[0]
        struct.pack_into('<Q',symbol_data,16*i+8,value-original_base)
output.extend(b'\0'*(-len(output)%8))
symbol_offset=len(output);output+=symbol_data
output.extend(b'\0'*(-len(output)%4))
indirect_offset=len(output);output+=indirect_data
string_offset=len(output);output+=string_data
struct.pack_into('<IIII',symtab_command,8,symbol_offset,nsyms,string_offset,len(string_data))
struct.pack_into('<I',dysymtab_command,56,indirect_offset)
linksize=len(output)-linkoff
struct.pack_into('<QQQQ',linkedit_command,24,linkedit_address-original_base,(linksize+4095)&~4095,linkoff,linksize)
new_commands=[*segment_commands,linkedit_command,*commands,symtab_command,dysymtab_command,
              bytearray(struct.pack('<II10I',0x80000022,48,*streams))]
command_data=b''.join(new_commands)
if 32+len(command_data)>header_capacity:
    raise ValueError(f'New load commands need {32+len(command_data)} bytes; original header capacity is {header_capacity}')
output[:header_capacity]=bytes(header_capacity)
output[:32]=data[:32]
struct.pack_into('<II',output,16,len(new_commands),len(command_data))
flags=struct.unpack_from('<I',output,24)[0]&~0x80000000
struct.pack_into('<I',output,24,flags)
output[32:32+len(command_data)]=command_data
destination=build/Path(image_path).name
temporary=destination.with_name(destination.name+'.pending')
temporary.write_bytes(output)
temporary.replace(destination)
report={'original_image_sha256':hashlib.sha256(data).hexdigest(),
        'staged_image_sha256':hashlib.sha256(output).hexdigest(),
        'rebases':len(rebases),'bindings':len(binds),'exports':len(exports),
        'lazy_bindings':len(lazy_binds),
        'lazy_binding_slots':[{'symbol':name,'provider':dependencies[ordinal-1] if ordinal else image_path,'offset':hex(address-original_base)}
            for address,(name,ordinal,weak,addend) in sorted(lazy_binds.items())],
        'pooled_slots_recovered':len(external_slots),'rip_instructions_patched':len(patched),
        'selectors_copied':len(strings),'patches':patched,
        'installed':False,'execution_verified':False}
report['modern_adapter']=modern_adapter
report['target']=args.target
if 'standalone_install_name' in image_config:report['standalone_install_name']=image_config['standalone_install_name']
report['reference_set']=reference_set
report['preferred_base']=0
report['redirected_imports']=sorted(redirected_imports)
report['compat_reexports']=compat_reexports
report['describe_lazy_helpers']=image_config.get('describe_lazy_helpers',True)
report['describe_compat_data']=image_config.get('describe_compat_data',True)
report['describe_leading_padding']=image_config.get('describe_leading_padding',True)
if args.experimental_swift:report['experimental_swift_unverified']=True
report['cache_imports']=image_config.get('cache_imports',{})
report['cache_u32_constants']=image_config.get('cache_u32_constants',{})
report['backend_call_overrides']=applied_overrides
report['cache_enum_case_literals']=image_config.get('cache_enum_case_literals',{})
report['function_resolvers']=function_resolvers
report['recovered_coalesced_data_imports']=[{'symbol':name,'provider':provider} for name,provider in sorted(coalesced_used)]
report['export_reexports']=export_reexports
if coalesced_segments:report['coalesced_page_segments']=coalesced_segments
if code_analysis is not None:report['code_analysis']=code_analysis
if swift_report is not None:
    swift_report['immortal_string_literals']=tagged_string_rebases
    report['swift_metadata']=swift_report
if objc_report is not None:report['objc_metadata']=objc_report
if tls_report is not None:report['tls_metadata']=tls_report
(build/'reconstruction.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='patches'},indent=2))
