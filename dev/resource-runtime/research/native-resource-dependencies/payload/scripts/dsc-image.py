#!/usr/bin/env python3
"""Read original cache image exports, including aliases and resolver stubs."""
from pathlib import Path
import runpy
import struct

project=Path(__file__).resolve().parent.parent
reference={key:globals()[key] for key in ('REFERENCE_CACHE_PATH','REFERENCE_LIBRARY_ROOT') if key in globals()}
cache=runpy.run_path(str(project/'scripts/inspect-dsc-constants.py'),init_globals=reference)
read,pointer=cache['read'],cache['pointer']
image_addresses={}
for ctx in cache['contexts']:
    for image in ctx.images:
        path=ctx.readString(image.pathFileOffset).rstrip(b'\0').decode()
        image_addresses[path]=image.address

def uleb_read(data,cursor):
    result=shift=0
    while True:
        value=data[cursor];cursor+=1
        result|=(value&127)<<shift
        if value<128:return result,cursor
        shift+=7
        if shift>63:raise ValueError('Invalid ULEB128')

def uleb(value):
    if value<0:raise ValueError('Negative ULEB128')
    out=bytearray()
    while value>=128:out.append((value&127)|128);value>>=7
    return bytes(out+bytes([value]))

class Image:
    def __init__(self,path):
        self.path=path
        self.base=image_addresses[path]
        header=read(self.base,32)
        if header[:4]!=b'\xcf\xfa\xed\xfe':raise ValueError('Unsupported cache image format')
        count,size=struct.unpack_from('<II',header,16)
        commands=read(self.base+32,size)
        self.dependencies=[];self.reexports=[];self.segments=[];self.sections=[]
        export_off=export_size=0
        cursor=0
        for _ in range(count):
            command,length=struct.unpack_from('<II',commands,cursor)
            if command==0x19:
                name=commands[cursor+8:cursor+24].split(b'\0')[0].decode()
                vmaddr,vmsize,fileoff,filesize=struct.unpack_from('<QQQQ',commands,cursor+24)
                self.segments.append((name,vmaddr,vmsize,fileoff,filesize))
                for index in range(struct.unpack_from('<I',commands,cursor+64)[0]):
                    at=cursor+72+80*index
                    section_name=commands[at:at+16].split(b'\0')[0].decode()
                    address,section_length=struct.unpack_from('<QQ',commands,at+32)
                    flags=struct.unpack_from('<I',commands,at+64)[0]
                    self.sections.append((section_name,name,address,section_length,flags))
            elif command in (0xc,0x80000018,0x8000001f,0x80000023):
                off=struct.unpack_from('<I',commands,cursor+8)[0]
                name=commands[cursor+off:cursor+length].split(b'\0')[0].decode()
                self.dependencies.append(name)
                if command==0x8000001f:self.reexports.append(name)
            elif command==0x80000033:
                export_off,export_size=struct.unpack_from('<II',commands,cursor+8)
            elif command in (0x22,0x80000022) and not export_size:
                export_off,export_size=struct.unpack_from('<II',commands,cursor+40)
            cursor+=length
        self.exports={}
        if export_size:
            segment=next(s for s in self.segments if s[0]=='__LINKEDIT')
            trie=read(segment[1]+export_off-segment[3],export_size)
            def visit(offset,prefix):
                size,c=uleb_read(trie,offset)
                end=c+size
                if size:
                    flags,c=uleb_read(trie,c)
                    if flags&8:
                        ordinal,c=uleb_read(trie,c)
                        name=trie[c:trie.index(0,c)].decode()
                        self.exports[prefix]=('reexport',ordinal,name)
                    else:
                        address,c=uleb_read(trie,c)
                        address=address if flags&3==2 else self.base+address
                        if flags&0x10:
                            resolver,c=uleb_read(trie,c)
                            self.exports[prefix]=('address',address,flags,self.base+resolver)
                        else:
                            self.exports[prefix]=('address',address,flags)
                c=end
                children=trie[c];c+=1
                for _ in range(children):
                    last=trie.index(0,c)
                    edge=trie[c:last].decode()
                    child,c=uleb_read(trie,last+1)
                    visit(child,prefix+edge)
            visit(0,'')

images={}
def image(path):
    # Framework load commands can name the unversioned symlink while the cache
    # records the canonical Versions/A (or C) path. Require a unique match.
    if path not in image_addresses and '.framework/' in path:
        prefix,tail=path.split('.framework/',1)
        if '/' not in tail:
            candidates=[candidate for candidate in image_addresses if candidate.startswith(prefix+'.framework/Versions/')
                and candidate.rsplit('/',1)[-1]==tail]
            if len(candidates)==1:path=candidates[0]
    if path not in images:images[path]=Image(path)
    return images[path]

def resolve(path,name,seen=None):
    seen=set() if seen is None else seen
    if (path,name) in seen:return None
    seen.add((path,name))
    obj=image(path)
    value=obj.exports.get(name)
    if value:
        if value[0]=='address':return value[1]
        return resolve(obj.dependencies[value[1]-1],value[2] or name,seen)
    for dependency in obj.reexports:
        found=resolve(dependency,name,seen)
        if found is not None:return found
    return None
