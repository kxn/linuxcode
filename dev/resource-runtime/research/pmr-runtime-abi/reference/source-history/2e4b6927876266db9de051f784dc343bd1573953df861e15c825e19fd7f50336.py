#!/usr/bin/env python3
"""Canonicalize weak-bind symbol order for classic dyld's merge iterator.

Preserve every binding (symbol, flags, type, segment, offset, addend) and every
symbol-only definition. No symbols, imports, code, or pointers are redirected.
"""
import hashlib,struct
def uleb(n):
    result=bytearray()
    while n>=128:result.append((n&127)|128);n>>=7
    result.append(n);return bytes(result)
def sleb(n):
    result=bytearray()
    while True:
        b=n&127;n>>=7;done=(n==0 and not b&64) or (n==-1 and b&64)
        result.append(b if done else b|128)
        if done:return bytes(result)
def decode(blob):
    blob=bytes(blob)
    cursor=0;symbols={};name=None;kind=1;segment=0;offset=0;addend=0
    def number(signed=False):
        nonlocal cursor
        value=shift=0
        while True:
            b=blob[cursor];cursor+=1;value|=(b&127)<<shift;shift+=7
            assert shift<=70
            if not b&128:break
        return value-(1<<shift) if signed and b&64 else value
    def bind():
        nonlocal offset
        assert name is not None and kind in [1,2,3]
        symbols[name]['bindings'].append((kind,segment,offset,addend))
        offset+=8 if kind==1 else 4
    while cursor<len(blob):
        value=blob[cursor];cursor+=1;op=value&240;imm=value&15
        if op==0:
            assert not any(blob[cursor:]);break
        elif op==0x40:
            end=blob.index(0,cursor);name=blob[cursor:end];cursor=end+1
            if name in symbols:assert symbols[name]['flags']==imm
            else:symbols[name]={'flags':imm,'bindings':[]}
        elif op==0x50:kind=imm
        elif op==0x60:addend=number(True)
        elif op==0x70:segment=imm;offset=number()
        elif op==0x80:offset+=number()
        elif op==0x90:bind()
        elif op==0xa0:bind();offset+=number()
        elif op==0xb0:bind();offset+=imm*8
        elif op==0xc0:
            count=number();skip=number();assert count<1000000
            for _ in range(count):bind();offset+=skip
        else:raise ValueError('Unsupported weak bind opcode '+hex(value))
    return symbols
def normalize(source):
    assert source[:8]==struct.pack('<II',0xfeedfacf,0x1000007)
    at=32;weak=None;link=None;sections=[]
    for _ in range(struct.unpack_from('<I',source,16)[0]):
        cmd,size=struct.unpack_from('<II',source,at)
        if cmd in [0x22,0x80000022]:weak=at+24
        elif cmd==0x19:
            if source[at+8:at+24].split(b'\0')[0]==b'__LINKEDIT':link=at
        elif cmd==0x1d:raise ValueError('Refuse a stale code signature')
        at+=size
    assert weak is not None and link is not None
    off,size=struct.unpack_from('<II',source,weak);old=decode(source[off:off+size])
    stream=bytearray()
    for name,data in sorted(old.items()):
        stream.extend(bytes([0x40|data['flags']])+name+b'\0')
        for kind,segment,offset,addend in data['bindings']:
            assert segment<16
            stream.extend(bytes([0x50|kind,0x60])+sleb(addend)+bytes([0x70|segment])+uleb(offset)+b'\x90')
    stream.append(0);stream.extend(bytes(-len(stream)%8))
    fresh=decode(stream);assert fresh==old
    # Classic dyld validates rebase/bind/weak/lazy/export order. Replace the
    # table in place and move the following LINKEDIT payload as an opaque block.
    # Eight-byte padding preserves symbol-table and other metadata alignment.
    cut=off+size;delta=len(stream)-size;assert delta%8==0
    binary=bytearray(source[:off]+stream+source[cut:]);allowed=set()
    def put32(where,value):
        struct.pack_into('<I',binary,where,value);allowed.update(range(where,where+4))
    def move32(where):
        value=struct.unpack_from('<I',source,where)[0]
        if value and value>=cut:put32(where,value+delta)
    at=32
    for _ in range(struct.unpack_from('<I',source,16)[0]):
        cmd,length=struct.unpack_from('<II',source,at)
        if cmd in [0x22,0x80000022]:
            for field in [8,16,24,32,40]:move32(at+field)
        elif cmd==2:
            move32(at+8);move32(at+16)
        elif cmd==0xb:
            for field in [32,40,48,56,64,72]:move32(at+field)
        elif cmd in [0x1e,0x26,0x29,0x2b,0x2e,0x80000033,0x80000034]:move32(at+8)
        elif cmd==0x16:move32(at+8)
        elif cmd==0x19:
            for j in range(struct.unpack_from('<I',source,at+64)[0]):
                section=at+72+80*j;fileoff=struct.unpack_from('<I',source,section+48)[0]
                assert not fileoff or fileoff<off,'Section in LINKEDIT is unsupported'
                assert struct.unpack_from('<I',source,section+56)[0]==0,'Section relocations unsupported'
        elif cmd not in [0xc,0xd,0xe,0x1b,0x80000018,0x8000001c,0x8000001f,0x80000028,0x20,0x24,0x25,0x27,0x2a,0x2f,0x30,0x32]:
            raise ValueError('Unsupported load command '+hex(cmd))
        at+=length
    put32(weak+4,len(stream))
    fileoff=struct.unpack_from('<Q',source,link+40)[0];length=len(binary)-fileoff
    struct.pack_into('<Q',binary,link+48,length);struct.pack_into('<Q',binary,link+32,(length+4095)&~4095)
    allowed.update(range(link+32,link+40));allowed.update(range(link+48,link+56))
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(source[:off],binary[:off])))
    assert binary[off+len(stream):]==source[cut:]
    report={'original_sha256':hashlib.sha256(source).hexdigest(),'normalized_sha256':hashlib.sha256(binary).hexdigest(),'original_symbol_order':[n.decode() for n in old],'normalized_symbol_order':[n.decode() for n in sorted(old)],'symbol_count':len(old),'binding_count':sum(len(v['bindings']) for v in old.values()),'all_symbol_flags_and_bindings_preserved':True,'instructions_and_other_payloads_unchanged':True,'following_linkedit_payload_preserved_byte_for_byte':True,'old_weak_range':[off,size],'new_weak_range':[off,len(stream)],'linkedit_payload_shift':delta}
    return bytes(binary),report
