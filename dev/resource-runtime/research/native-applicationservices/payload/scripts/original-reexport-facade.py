"""Strict structural checks for a code-free original framework reexport facade."""
import hashlib
import struct
import runpy
from pathlib import Path

def version_constants(data,info):
    table=runpy.run_path(str(Path(__file__).with_name('verify-dysymtab-alias-repair.py')))['tables'](data)
    identity=[raw for kind,at,raw in info['commands'] if kind==0xd]
    if len(identity)!=1:raise ValueError('Expected one facade install identity')
    raw=identity[0];off=struct.unpack_from('<I',raw,8)[0]
    name=Path(raw[off:raw.index(0,off)].decode()).name
    if not name.isidentifier():raise ValueError('Unsupported version symbol prefix')
    expected={'_'+name+'VersionNumber','_'+name+'VersionString'}
    if len(table['records'])!=2 or set(table['names'])!=expected:
        raise ValueError('Expected only original facade version symbols')
    if list(table['dynamic'][:6])!=[0,0,0,2,2,0] or table['indirect']:
        raise ValueError('Unexpected facade symbol groups or indirect symbols')
    if any(table['dynamic'][6:12]+table['dynamic'][13:]):
        raise ValueError('Unexpected facade symbol side tables')
    address,size,off,flags=info['sections']['__TEXT','__const']
    if not 0<size<=4096 or flags:raise ValueError('Unsupported facade constants section')
    for name,record in zip(table['names'],table['records']):
        _,kind,section,desc,value=record
        if (kind,section,desc)!=(0xf,2,0) or not address<=value<address+size:
            raise ValueError('Unsupported version symbol identity or extent')
        if name.endswith('Number'):
            if value%8 or value+8>address+size:raise ValueError('Invalid version number extent')
        elif b'\0' not in data[off+value-address:off+size]:
            raise ValueError('Unterminated facade version string')
    return dict(bytes=size,sha256=hashlib.sha256(data[off:off+size]).hexdigest(),
                symbols=table['names'],values={n:r[4] for n,r in zip(table['names'],table['records'])})

def layout(data):
    if len(data)<32 or data[:8]!=bytes.fromhex('cffaedfe07000001'):
        raise ValueError('Expected an Intel Mach-O dylib')
    if struct.unpack_from('<I',data,12)[0]!=6:
        raise ValueError('Expected a dylib facade')
    count,total=struct.unpack_from('<II',data,16)
    if 32+total>len(data):raise ValueError('Truncated facade commands')
    sections={};commands=[];dependencies=[];at=32;uuid=None
    for _ in range(count):
        if at+8>32+total:raise ValueError('Truncated facade command')
        kind,size=struct.unpack_from('<II',data,at)
        if size<8 or size%8 or at+size>32+total:raise ValueError('Invalid facade command extent')
        raw=data[at:at+size];commands.append((kind,at,raw))
        if kind==0x19:
            if size<72:raise ValueError('Truncated facade segment')
            seg=raw[8:24].split(b'\0')[0].decode();n=struct.unpack_from('<I',raw,64)[0]
            if size!=72+80*n:raise ValueError('Invalid facade section table')
            for i in range(n):
                off=72+80*i;name=raw[off:off+16].split(b'\0')[0].decode()
                addr,length,fileoff=struct.unpack_from('<QQI',raw,off+32)
                reloff,nreloc,flags=struct.unpack_from('<III',raw,off+56)
                if (seg,name) in sections or reloff or nreloc or fileoff+length>len(data):
                    raise ValueError('Invalid facade section')
                sections[seg,name]=(addr,length,fileoff,flags)
        elif kind in (0xc,0x80000018,0x8000001f,0x80000023):
            offset=struct.unpack_from('<I',raw,8)[0]
            if not 24<=offset<size or b'\0' not in raw[offset:]:
                raise ValueError('Invalid facade dependency name')
            name=raw[offset:raw.index(0,offset)].decode()
            if not name.startswith('/') or '..' in name.split('/'):
                raise ValueError('Invalid facade dependency path')
            dependencies.append((kind,name))
        elif kind==0x1b:
            if size!=24 or uuid is not None:raise ValueError('Invalid facade UUID')
            uuid=raw[8:24].hex()
        at+=size
    if at!=32+total or uuid is None:raise ValueError('Invalid facade header')
    return dict(sections=sections,commands=commands,dependencies=dependencies,uuid=uuid)

def validate_original(data):
    info=layout(data);sections=info['sections']
    imageinfo=set(sections)=={('__TEXT','__text'),('__DATA_CONST','__objc_imageinfo')}
    constants=set(sections)=={('__TEXT','__text'),('__TEXT','__const')}
    if not imageinfo and not constants:
        raise ValueError('Unsupported facade section set')
    if sections['__TEXT','__text'][1]:raise ValueError('Facade must contain no executable bytes')
    if imageinfo:
        if sections['__DATA_CONST','__objc_imageinfo'][1]!=8:raise ValueError('Expected one image-info record')
        at=sections['__DATA_CONST','__objc_imageinfo'][2]
        if struct.unpack_from('<I',data,at)[0]:raise ValueError('Unsupported facade image-info version')
    else:
        version_constants(data,info)
        if any(k not in {0x19,0xd,0x80000033,2,0xb,0x1b,0x32,0x2a,0xc,
                         0x80000018,0x8000001f,0x80000023,0x26,0x29}
               for k,at,raw in info['commands']):
            raise ValueError('Unexpected constant facade command')
    if not any(kind==0x8000001f for kind,name in info['dependencies']):
        raise ValueError('Facade has no original reexports')
    for kind,at,raw in info['commands']:
        if kind==2 and struct.unpack_from('<I',raw,12)[0]!=(2 if constants else 0):
            raise ValueError('Facade contains symbol records')
        if kind==0x80000033 and struct.unpack_from('<I',raw,12)[0]:
            raise ValueError('Facade contains export payload')
        if kind in (0x26,0x29):
            offset,size=struct.unpack_from('<II',raw,8)
            if offset+size>len(data) or any(data[offset:offset+size]):
                raise ValueError('Facade contains function/data-in-code records')
        if kind in (0x22,0x80000022,0x80000034,0x1d,0x80000028,0x4,0x5):
            raise ValueError('Unsupported executable/fixup facade command')
    proof=dict(original_sha256=hashlib.sha256(data).hexdigest(),original_uuid=info['uuid'],
        original_executable_bytes=0,original_dependencies=info['dependencies'],
        reexport_count=sum(kind==0x8000001f for kind,name in info['dependencies']))
    if imageinfo:
        at=sections['__DATA_CONST','__objc_imageinfo'][2]
        proof['original_imageinfo']=data[at:at+8].hex()
    else:proof['original_version_constants']=version_constants(data,info)
    return proof

def inspect(original,candidate):
    proof=validate_original(original);before=layout(original);after=layout(candidate)
    allowed={0x19,0xd,0x2,0xb,0x1b,0x32,0x2a,0xc,0x80000018,0x8000001f,0x80000023,0x80000022}
    if any(kind not in allowed for kind,_,_ in after['commands']):
        raise ValueError('Unexpected candidate facade command')
    for kind,_,raw in after['commands']:
        if kind==2 and struct.unpack_from('<I',raw,12)[0]!=(2 if 'original_version_constants' in proof else 0):
            raise ValueError('Candidate facade contains symbol records')
    if before['dependencies']!=after['dependencies'] or before['uuid']!=after['uuid']:
        raise ValueError('Original facade dependencies/UUID changed')
    for kind in (0xd,0xc,0x80000018,0x8000001f,0x80000023,0x32):
        if [raw for k,_,raw in before['commands'] if k==kind]!=[raw for k,_,raw in after['commands'] if k==kind]:
            raise ValueError('Original facade identity/dependency/build commands changed')
    if set(after['sections'])!=set(before['sections']):raise ValueError('Candidate facade sections changed')
    if after['sections']['__TEXT','__text'][1]:raise ValueError('Candidate facade acquired executable bytes')
    if after['sections']['__TEXT','__text'][3]!=before['sections']['__TEXT','__text'][3]:
        raise ValueError('Candidate facade executable section flags changed')
    base=next(struct.unpack_from('<Q',raw,24)[0] for k,_,raw in before['commands']
        if k==0x19 and raw[8:24].split(b'\0')[0]==b'__TEXT')
    if 'original_version_constants' in proof:
        for key,(addr,size,off,flags) in before['sections'].items():
            newaddr,newsize,newoff,newflags=after['sections'][key]
            if (newaddr,newsize,newflags)!=(addr-base,size,flags) or candidate[newoff:newoff+size]!=original[off:off+size]:
                raise ValueError('Candidate facade original section bytes/layout changed')
        version_constants(candidate,after)
        proof['version_symbol_identity']=runpy.run_path(str(Path(__file__).with_name(
            'verify-dysymtab-alias-repair.py')))['verify'](original,candidate)
        proof['original_version_constants_byte_equal']=True
    else:
        addr,size,off,flags=after['sections']['__DATA_CONST','__objc_imageinfo']
        oldaddr,oldsize,oldoff,oldflags=before['sections']['__DATA_CONST','__objc_imageinfo']
        if size!=8 or flags!=oldflags:raise ValueError('Candidate facade image-info layout changed')
        if addr!=oldaddr-base:raise ValueError('Candidate facade image-info address changed')
        version,flags=struct.unpack_from('<II',original,oldoff)
        if candidate[off:off+8]!=struct.pack('<II',version,flags&~(1|8|16|128)):
            raise ValueError('Candidate facade image-info bytes changed')
        proof['original_imageinfo_only_preoptimization_flags_cleared']=True
    dyld=[raw for k,_,raw in after['commands'] if k in (0x22,0x80000022)]
    if len(dyld)!=1:raise ValueError('Expected one classic facade fixup description')
    streams=struct.unpack_from('<10I',dyld[0],8)
    if streams[5] or streams[7]:raise ValueError('Unexpected facade weak/lazy bindings')
    bindoff,bindsize=streams[2:4]
    expoff,expsize=streams[8:10]
    if candidate[bindoff:bindoff+bindsize]!=b'\0':raise ValueError('Unexpected facade bindings')
    if 'original_version_constants' in proof:
        helper=runpy.run_path(str(Path(__file__).with_name('macho-named-reexport.py')))
        expected={n.encode():helper['uleb'](0)+helper['uleb'](v-base)
                  for n,v in proof['original_version_constants']['values'].items()}
        if helper['entries'](candidate[expoff:expoff+expsize])!=expected:
            raise ValueError('Facade version export names/flags/addresses changed')
        proof['version_export_names_flags_addresses_preserved']=True
    elif candidate[expoff:expoff+expsize]!=b'\0\0':raise ValueError('Unexpected facade exports')
    offset,size=streams[:2]
    if candidate[offset:offset+size]!=b'\x11\0':raise ValueError('Unexpected facade rebase operations')
    proof.update(verified=True,candidate_sha256=hashlib.sha256(candidate).hexdigest(),
        original_dependency_commands_byte_equal=True,
        original_machine_code_reimplemented=False,runtime_execution_verified=False)
    return proof
