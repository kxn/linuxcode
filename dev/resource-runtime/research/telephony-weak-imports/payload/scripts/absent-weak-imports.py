#!/usr/bin/env python3
"""Audit absent original weak dylibs without inventing their implementations."""
from pathlib import Path
import hashlib
import struct

def audit(data, library_root, image_lookup):
    if data[:8] != bytes.fromhex('cffaedfe07000001'):
        raise ValueError('Expected original x86_64 Mach-O')
    dependencies, weak, symbols = [], set(), []
    at = 32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size = struct.unpack_from('<II',data,at)
        if size < 8 or at+size > len(data):
            raise ValueError('Invalid original load command')
        if command in (0xc,0x80000018,0x8000001f,0x80000023):
            offset = struct.unpack_from('<I',data,at+8)[0]
            if not 24 <= offset < size: raise ValueError('Invalid dependency name offset')
            provider = data[at+offset:data.index(0,at+offset,at+size)].decode()
            if not provider.startswith('/') or '..' in Path(provider).parts:
                raise ValueError('Invalid original dependency path')
            dependencies.append(provider)
            if command == 0x80000018: weak.add(len(dependencies))
        elif command == 2:
            symoff,count,stroff,strsize = struct.unpack_from('<4I',data,at+8)
            if symoff+count*16 > len(data) or stroff+strsize > len(data):
                raise ValueError('Invalid original symbol table')
            for index in range(count):
                name,kind,section,desc,value = struct.unpack_from('<IBBHQ',data,symoff+16*index)
                if kind & 0xe or not kind & 1: continue
                if name >= strsize: raise ValueError('Invalid original symbol name')
                text = data[stroff+name:data.index(0,stroff+name,stroff+strsize)].decode()
                symbols.append((text,desc,value))
        at += size
    result = []
    for ordinal in sorted(weak):
        provider = dependencies[ordinal-1]
        try: image_lookup(provider)
        except KeyError:
            if (Path(library_root)/provider.lstrip('/')).exists():
                raise ValueError('Weak provider is present outside the reference cache')
            names = []
            for name,desc,value in symbols:
                if desc >> 8 != ordinal: continue
                if not desc & 0x40 or value != 0:
                    raise ValueError('Absent provider has a strong or nonzero original import')
                names.append(name)
            result.append(dict(provider=provider,ordinal=ordinal,load_command='0x80000018',
                undefined_weak_symbols=sorted(names),original_provider_absent=True))
    return dict(original_image_sha256=hashlib.sha256(data).hexdigest(),dependencies=result)
