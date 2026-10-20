#!/usr/bin/env python3
"""Audit actual eager/lazy dyld bindings in an already inventoried closure.

Static diagnosis only: exported names do not establish ABI/API compatibility.
Uses the exact host images selected by inventory-runtime-dependencies.py, with
their re-export chains, rather than the exports of the original Apple cache.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import struct

root = Path(__file__).resolve().parent.parent


def uleb(data, at):
    value = shift = 0
    while True:
        byte = data[at]; at += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, at
        shift += 7
        if shift > 63:
            raise ValueError('Invalid ULEB128')


def sleb(data, at):
    value = shift = 0
    while True:
        byte = data[at]; at += 1
        value |= (byte & 127) << shift
        shift += 7
        if byte < 128:
            return value - (1 << shift) if byte & 64 else value, at
        if shift > 70:
            raise ValueError('Invalid SLEB128')


class Image:
    def __init__(self, record):
        self.record = record
        data = (root / record['host']).read_bytes()
        self.host_sha256 = hashlib.sha256(data).hexdigest()
        if data[:4] in (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf'):
            endian = '<' if data[:4] == b'\xbe\xba\xfe\xca' else '>'
            width = 32 if data[:4] == b'\xca\xfe\xba\xbf' else 20
            for i in range(struct.unpack_from(endian + 'I', data, 4)[0]):
                at = 8 + i * width
                if struct.unpack_from(endian + 'I', data, at)[0] == 0x1000007:
                    off, size = struct.unpack_from(endian + ('QQ' if width == 32 else 'II'), data, at + 8)
                    data = data[off:off + size]
                    break
            else:
                raise ValueError('Missing x86_64 slice')
        if data[:4] != b'\xcf\xfa\xed\xfe':
            raise ValueError('Unsupported image ' + record['host'])
        self.dependencies = []; self.reexports = []; self.exports = {}
        self.bindings = []; self.install_name = None; self.chained_fixups = False
        export_off = export_size = 0
        streams = []; at = 32
        for _ in range(struct.unpack_from('<I', data, 16)[0]):
            cmd, size = struct.unpack_from('<II', data, at)
            if size < 8 or at + size > len(data):
                raise ValueError('Invalid load command')
            if cmd in (0xc, 0xd, 0x80000018, 0x8000001f, 0x80000023):
                name_at = at + struct.unpack_from('<I', data, at + 8)[0]
                name = data[name_at:data.index(0, name_at)].decode()
                if cmd == 0xd:
                    self.install_name = name
                else:
                    self.dependencies.append(name)
                    if cmd == 0x8000001f:
                        self.reexports.append(len(self.dependencies))
            elif cmd in (0x22, 0x80000022):
                fields = struct.unpack_from('<10I', data, at + 8)
                streams.extend([(fields[2], fields[3], 'eager'), (fields[6], fields[7], 'lazy')])
                if not export_size:
                    export_off, export_size = fields[8:10]
            elif cmd == 0x80000033:
                export_off, export_size = struct.unpack_from('<II', data, at + 8)
            elif cmd == 0x80000034:
                self.chained_fixups = struct.unpack_from('<I', data, at + 12)[0] != 0
            at += size
        if export_size:
            trie = data[export_off:export_off + export_size]

            def visit(at, name):
                size, cursor = uleb(trie, at)
                end = cursor + size
                if size:
                    flags, cursor = uleb(trie, cursor)
                    if flags & 8:
                        ordinal, cursor = uleb(trie, cursor)
                        imported = trie[cursor:trie.index(0, cursor)].decode()
                        self.exports[name] = (ordinal, imported or name)
                    else:
                        self.exports[name] = None
                count = trie[end]; cursor = end + 1
                for _ in range(count):
                    edge_end = trie.index(0, cursor)
                    edge = trie[cursor:edge_end].decode()
                    child, cursor = uleb(trie, edge_end + 1)
                    visit(child, name + edge)

            visit(0, '')
        for off, size, mode in streams:
            stream = data[off:off + size]
            at = ordinal = flags = 0; name = None

            def bind():
                if name is None:
                    raise ValueError('Bind without symbol')
                self.bindings.append((name, ordinal, bool(flags & 1), mode))

            while at < len(stream):
                opcode = stream[at] & 0xf0; imm = stream[at] & 15; at += 1
                if opcode == 0:
                    if mode == 'eager':
                        break
                    ordinal = flags = 0; name = None
                elif opcode == 0x10:
                    ordinal = imm
                elif opcode == 0x20:
                    ordinal, at = uleb(stream, at)
                elif opcode == 0x30:
                    ordinal = imm - 16 if imm else 0
                elif opcode == 0x40:
                    end = stream.index(0, at); name = stream[at:end].decode(); at = end + 1; flags = imm
                elif opcode == 0x50:
                    pass
                elif opcode == 0x60:
                    _, at = sleb(stream, at)
                elif opcode in (0x70, 0x80):
                    _, at = uleb(stream, at)
                elif opcode in (0x90, 0xb0):
                    bind()
                elif opcode == 0xa0:
                    bind(); _, at = uleb(stream, at)
                elif opcode == 0xc0:
                    count, at = uleb(stream, at); _, at = uleb(stream, at)
                    for _ in range(count):
                        bind()
                else:
                    raise ValueError('Unsupported binding opcode: ' + hex(opcode))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, default=root / 'artifacts/native-dependency-inventory.json')
    parser.add_argument('--output', type=Path, default=root / 'artifacts/native-symbol-audit.json')
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    images = [Image(record) for record in inventory['images']]
    aliases = {}
    for image in images:
        aliases[image.record['image']] = image
        for alias in image.record.get('aliases',[]):
            aliases[alias] = image
        if image.install_name:
            aliases[image.install_name] = image
    # DYLD search substitutions (e.g. /usr/lib/swift and framework staging)
    # can cause distinct load names to select the same inventory image.
    def provider(name):
        if name in aliases:
            return aliases[name]
        candidates = [i for i in images if Path(i.record['image']).name == Path(name).name]
        return candidates[0] if len(candidates) == 1 else None

    def exported(image, name, seen):
        if image is None or (id(image), name) in seen:
            return False
        seen = seen | {(id(image), name)}
        if name in image.exports:
            entry = image.exports[name]
            if entry is None:
                return True
            ordinal, symbol = entry
            return 0 < ordinal <= len(image.dependencies) and exported(provider(image.dependencies[ordinal - 1]), symbol, seen)
        return any(exported(provider(image.dependencies[o - 1]), name, seen) for o in image.reexports)

    missing = {}; special = Counter(); checked = 0
    for image in images:
        for name, ordinal, weak, mode in image.bindings:
            checked += 1
            if ordinal < 0:
                special[str(ordinal)] += 1
                continue
            expected = image.dependencies[ordinal - 1] if ordinal else image.install_name
            target = provider(expected) if ordinal else image
            if exported(target, name, set()):
                continue
            key = (image.record['image'], expected, name, weak, mode)
            missing[key] = {'consumer': key[0], 'provider': expected, 'symbol': name,
                            'weak_import': weak, 'binding': mode, 'provider_in_inventory': target is not None}
    rows = sorted(missing.values(), key=lambda r: (r['binding'], r['weak_import'], r['consumer'], r['symbol']))
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': __doc__,
              'inventory': str(args.inventory), 'images': len(images), 'binding_slots_checked': checked,
              'image_sha256': {i.record['host']: i.host_sha256 for i in images},
              'chained_binding_images_not_audited': [i.record['host'] for i in images if i.chained_fixups],
              'special_lookup_ordinals_not_audited': dict(special), 'unresolved': rows,
              'full_compatibility': False}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'images': len(images), 'slots': checked,
                      'unresolved': dict(Counter((r['binding'] + ('_weak' if r['weak_import'] else '_strong')) for r in rows))}))


if __name__ == '__main__':
    main()
