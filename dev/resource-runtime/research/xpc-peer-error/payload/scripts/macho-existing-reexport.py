"""Add named exports from an existing dependency without adding an init edge."""
import runpy
import struct
from pathlib import Path

helper = runpy.run_path(str(Path(__file__).with_name('macho-named-reexport.py')))


def add(source, provider, names):
    assert source[:8] == bytes.fromhex('cffaedfe07000001')
    at = 32
    dependencies = []
    export = linkedit = None
    for _ in range(struct.unpack_from('<I', source, 16)[0]):
        command, size = struct.unpack_from('<II', source, at)
        if command in (0xc, 0x80000018, 0x8000001f, 0x80000023, 0x20):
            start = at+struct.unpack_from('<I', source, at+8)[0]
            dependencies.append(source[start:source.index(0, start)].decode())
        elif command == 0x19 and source[at+8:at+24].split(b'\0')[0] == b'__LINKEDIT':
            linkedit = at
        elif command in (0x22, 0x80000022, 0x80000033):
            export = at+(8 if command == 0x80000033 else 40)
        elif command == 0x1d:
            raise ValueError('Refuse a stale code signature')
        at += size
    assert export is not None and linkedit is not None and dependencies.count(provider) == 1
    ordinal = dependencies.index(provider)+1
    off, size = struct.unpack_from('<II', source, export)
    old = helper['entries'](source[off:off+size])
    new = dict(old)
    assert names and len(set(names)) == len(names)
    for name in names:
        assert name.encode() not in new
        new[name.encode()] = helper['uleb'](8)+helper['uleb'](ordinal)+b'\0'
    fresh = helper['trie'](new)
    assert helper['entries'](fresh) == new
    result = bytearray(source)
    result.extend(bytes(-len(result) % 8))
    off = len(result)
    result.extend(fresh)
    struct.pack_into('<II', result, export, off, len(fresh))
    fileoff = struct.unpack_from('<Q', source, linkedit+40)[0]
    length = len(result)-fileoff
    struct.pack_into('<Q', result, linkedit+48, length)
    struct.pack_into('<Q', result, linkedit+32, (length+4095) & ~4095)
    allowed = set(range(export, export+8)) | set(range(linkedit+32, linkedit+40)) | set(range(linkedit+48, linkedit+56))
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result)))
    assert all(new[name] == terminal for name, terminal in old.items())
    return bytes(result), dict(original_export_payloads_preserved=len(old), added_names=names,
        original_instructions_and_other_bytes_preserved=True, added_dependency_edges=0,
        provider_ordinal=ordinal)
