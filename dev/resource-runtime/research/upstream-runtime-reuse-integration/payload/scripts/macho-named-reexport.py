#!/usr/bin/env python3
"""Add explicitly named reexports; preserve old payloads, code and other bytes."""
import struct

def uleb(value):
    out=bytearray()
    while value>=128:out.append((value&127)|128);value>>=7
    return bytes(out+bytes([value]))

def entries(blob):
    result={}
    if not blob:return result
    def take(at):
        value=shift=0
        while True:
            byte=blob[at];at+=1;value|=(byte&127)<<shift
            if byte<128:return value,at
            shift+=7;assert shift<64
    def visit(at,prefix):
        n,at=take(at)
        if n:result[prefix]=blob[at:at+n]
        at+=n;children=blob[at];at+=1
        for _ in range(children):
            end=blob.index(0,at);edge=blob[at:end];offset,at=take(end+1);visit(offset,prefix+edge)
    visit(0,b'');return result

def trie(exports):
    nodes=[]
    def node(names,prefix):
        n=dict(terminal=exports.get(prefix,b''),children=[],offset=0);nodes.append(n)
        remaining=[s for s in names if s!=prefix]
        for first in sorted(set(s[len(prefix)] for s in remaining)):
            group=[s for s in remaining if s[len(prefix)]==first];common=group[0]
            for s in group[1:]:
                at=len(prefix)
                while at<min(len(common),len(s)) and common[at]==s[at]:at+=1
                common=common[:at]
            n['children'].append((common[len(prefix):],node(group,common)))
        return n
    node(list(exports),b'')
    def encode(n):
        return uleb(len(n['terminal']))+n['terminal']+bytes([len(n['children'])])+b''.join(edge+b'\0'+uleb(child['offset']) for edge,child in n['children'])
    for _ in range(100):
        at=0;changed=False
        for n in nodes:changed|=n['offset']!=at;n['offset']=at;at+=len(encode(n))
        if not changed:break
    else:raise ValueError('Export offsets did not converge')
    return b''.join(encode(n) for n in nodes)

def add(source,library,names,*,replace_existing=False):
    assert source[:4]==b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I',source,4)[0]==0x1000007
    binary=bytearray(source);at=32;dependencies=[];sections=[];ranges=[];export=None
    for _ in range(struct.unpack_from('<I',source,16)[0]):
        cmd,size=struct.unpack_from('<II',source,at)
        if cmd==0x19:
            if source[at+8:at+24].split(b'\0')[0]==b'__LINKEDIT':linkedit=at
            for j in range(struct.unpack_from('<I',source,at+64)[0]):
                s=at+72+80*j;off=struct.unpack_from('<I',source,s+48)[0];length=struct.unpack_from('<Q',source,s+40)[0]
                if off:sections.append(off)
                if struct.unpack_from('<I',source,s+64)[0]&0x80000400:ranges.append((off,length))
        elif cmd in (0x22,0x80000022):export=at+40
        elif cmd==0x80000033:export=at+8
        elif cmd in (0xc,0x80000018,0x8000001f,0x80000023,0x20):dependencies.append(at)
        elif cmd==0x1d:raise ValueError('Do not retain a stale code signature')
        at+=size
    assert export is not None and names
    path=library.encode()+b'\0';size=(24+len(path)+7)&~7
    assert at+size<=min(sections) and not any(source[at:at+size])
    # Load the provider without reexporting its entire namespace.
    binary[at:at+size]=struct.pack('<6I',0xc,size,24,0,0x10000,0x10000)+path.ljust(size-24,b'\0')
    struct.pack_into('<I',binary,16,struct.unpack_from('<I',source,16)[0]+1)
    struct.pack_into('<I',binary,20,struct.unpack_from('<I',source,20)[0]+size)
    offset,length=struct.unpack_from('<II',source,export);old=entries(source[offset:offset+length]);new=dict(old)
    for name in names:
        assert replace_existing or name.encode() not in old
        new[name.encode()]=uleb(8)+uleb(len(dependencies)+1)+b'\0'
    fresh=trie(new);assert entries(fresh)==new
    binary.extend(bytes(-len(binary)%8));offset=len(binary);binary.extend(fresh)
    struct.pack_into('<II',binary,export,offset,len(fresh))
    fileoff=struct.unpack_from('<Q',source,linkedit+40)[0];filesize=len(binary)-fileoff
    struct.pack_into('<Q',binary,linkedit+48,filesize);struct.pack_into('<Q',binary,linkedit+32,(filesize+4095)&~4095)
    allowed=set(range(16,24))|set(range(at,at+size))|set(range(export,export+8))|set(range(linkedit+32,linkedit+40))|set(range(linkedit+48,linkedit+56))
    assert all(a==b or j in allowed for j,(a,b) in enumerate(zip(source,binary)))
    for start,length in ranges:assert binary[start:start+length]==source[start:start+length]
    replaced={name.encode() for name in names if name.encode() in old}
    assert all(new[key]==payload for key,payload in old.items() if key not in replaced)
    return bytes(binary),dict(original_export_payloads_preserved=len(old)-len(replaced),added_names=[n for n in names if n.encode() not in old],redirected_names=[n for n in names if n.encode() in replaced],
        original_instructions_and_other_bytes_preserved=True,provider_entire_namespace_reexported=False)
