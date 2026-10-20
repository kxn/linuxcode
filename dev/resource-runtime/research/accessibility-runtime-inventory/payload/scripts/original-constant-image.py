"""Validate original constant-only Intel images without inventing code or GOTs.

This deliberately supports the observed libSpatial shape only: empty text,
one constant section, private version symbols, no exported API or fixups.
"""
from pathlib import Path
import hashlib
import runpy
import struct

here=Path(__file__).resolve().parent
layout=runpy.run_path(str(here/'original-reexport-facade.py'))['layout']
symbols=runpy.run_path(str(here/'verify-dysymtab-alias-repair.py'))


def validate_original(data):
    info=layout(data)
    sections=info['sections']
    assert set(sections)=={('__TEXT','__text'),('__TEXT','__const')}
    assert sections['__TEXT','__text'][1]==0
    addr,size,off,flags=sections['__TEXT','__const']
    assert size and flags==0
    assert info['dependencies']==[(0xc,'/usr/lib/libSystem.B.dylib')]
    allowed={0x19,0xd,0x80000033,2,0xb,0x1b,0x32,0x2a,0xc,0x26,0x29}
    assert all(k in allowed for k,_,_ in info['commands'])
    for k,_,raw in info['commands']:
        if k in (0x80000033,0x26,0x29):
            start,length=struct.unpack_from('<II',raw,8)
            assert start+length<=len(data)
            assert not any(data[start:start+length]), 'Unexpected exports/functions/data-in-code'
    table=symbols['tables'](data)
    assert not table['indirect']
    assert len(table['records'])==2
    assert set(table['names'])=={'_SpatialVersionString','_SpatialVersionNumber'}
    for name,record in zip(table['names'],table['records']):
        _,kind,section,desc,value=record
        assert (kind,section,desc)==(0x1e,2,0)
        assert addr<=value<addr+size
        if name.endswith('Number'):assert value+8<=addr+size
        else:assert b'\0' in data[off+value-addr:off+size]
    assert list(table['dynamic'][:6])==[0,2,2,0,2,0]
    assert not any(table['dynamic'][6:12]+table['dynamic'][13:])
    return dict(original_sha256=hashlib.sha256(data).hexdigest(),
                original_uuid=info['uuid'],original_executable_bytes=0,
                constants_sha256=hashlib.sha256(data[off:off+size]).hexdigest(),
                constant_bytes=size,private_version_symbols=table['names'],
                original_dependencies=info['dependencies'])


def inspect(original,candidate):
    result=validate_original(original)
    before,after=layout(original),layout(candidate)
    assert before['dependencies']==after['dependencies']
    assert before['uuid']==after['uuid']
    assert set(before['sections'])==set(after['sections'])
    assert all(k in {0x19,0xd,2,0xb,0x1b,0x32,0x2a,0xc,0x80000022}
               for k,_,_ in after['commands'])
    for kind in (0xd,0xc,0x32,0x2a):
        assert [raw for k,_,raw in before['commands'] if k==kind]==[
            raw for k,_,raw in after['commands'] if k==kind]
    base=next(struct.unpack_from('<Q',raw,24)[0] for k,_,raw in before['commands']
              if k==0x19 and raw[8:24].rstrip(b'\0')==b'__TEXT')
    for key,(address,size,off,flags) in before['sections'].items():
        newaddr,newsize,newoff,newflags=after['sections'][key]
        assert (newaddr,newsize,newflags)==(address-base,size,flags)
        assert original[off:off+size]==candidate[newoff:newoff+size]
    dyld=[raw for k,_,raw in after['commands'] if k==0x80000022]
    assert len(dyld)==1
    streams=struct.unpack_from('<10I',dyld[0],8)
    for index,expected in [(0,b'\x11\0'),(2,b'\0'),(4,b''),(6,b''),(8,b'\0\0')]:
        off,size=streams[index:index+2]
        assert size==len(expected) and candidate[off:off+size]==expected
    result.update(verified=True,original_constants_byte_equal=True,
                  symbol_identity=symbols['verify'](original,candidate),
                  candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                  runtime_behavior_verified=False)
    return result
