#!/usr/bin/env python3
"""Validate native text-section literals against pinned upstream data directives.

This recognizes literal data, not arbitrary executable ranges. Source slices
must contain only integer data directives/labels, must match uniquely in the
native instruction section, have real data readers and no direct code entry.
"""
from pathlib import Path
import hashlib, re, struct, sys

def literal_bytes(record, root):
    source = root / record['source']
    payload = source.read_bytes()
    if hashlib.sha256(payload).hexdigest() != record['source_sha256']:
        raise ValueError('Upstream assembly source changed')
    lines = payload.decode().splitlines()
    first, last = record['first_line'], record['last_line']
    if not 1 <= first <= last <= len(lines):
        raise ValueError('Invalid source literal extent')
    data = bytearray()
    labels = {}
    if first > 1 and lines[first - 2].strip().endswith(':'):
        labels[lines[first - 2].strip()[:-1]] = 0
    for line in lines[first - 1:last]:
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r'[A-Za-z_.$][\w.$]*:', line):
            labels[line[:-1]] = len(data)
            continue
        match = re.fullmatch(r'\.(byte|value|long|quad)\s+(.+)', line)
        if not match:
            raise ValueError('Source slice contains something other than literal data: ' + line)
        width = {'byte': 1, 'value': 2, 'long': 4, 'quad': 8}[match[1]]
        for token in match[2].split(','):
            if not re.fullmatch(r'\s*(?:0x[0-9a-fA-F]+|[0-9]+)\s*', token):
                raise ValueError('Expected an unsigned literal integer')
            data += int(token, 0).to_bytes(width, 'little')
    if not data or len(data) != record['length'] or hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('Source literal bytes/length changed')
    return bytes(data), labels

def validate(disassembly, records, base, read, functions, source, root):
    source = bytes(Path(source).read_bytes())
    cursor = 32
    text = None
    symbols = {}
    for _ in range(struct.unpack_from('<I', source, 16)[0]):
        command, size = struct.unpack_from('<II', source, cursor)
        if command == 0x19:
            for i in range(struct.unpack_from('<I', source, cursor + 64)[0]):
                at = cursor + 72 + 80 * i
                if source[at:at + 16].split(b'\0')[0] == b'__text':
                    text = struct.unpack_from('<QQ', source, at + 32)
        elif command == 2:
            offset, count, strings, length = struct.unpack_from('<IIII', source, cursor + 8)
            for i in range(count):
                name, kind, section, desc, value = struct.unpack_from('<IBBHQ', source, offset + 16 * i)
                if kind & 0xe == 0xe:
                    label = source[strings + name:source.index(0, strings + name)].decode()
                    symbols.setdefault(value, set()).add(label)
        cursor += size
    if text is None:
        raise ValueError('No native instruction section')
    result = []
    native_text = read(text[0], text[1])
    for record in records:
        payload, labels = literal_bytes(record, root)
        start = base + int(record['offset'], 0)
        end = start + len(payload)
        if not text[0] <= start < end <= text[0] + text[1]:
            raise ValueError('Literal is outside the native instruction section')
        if read(start, len(payload)) != payload:
            raise ValueError('Native bytes differ from upstream assembly literals')
        if native_text.count(payload) != 1:
            raise ValueError('Upstream literal match is not unique in native text')
        entries = []
        for address in functions:
            if start <= address < end:
                expected = {n for n, offset in labels.items() if start + offset == address}
                if not expected.intersection(symbols.get(address, set())):
                    raise ValueError('Unexplained function entry inside literal data')
                entries.append(dict(address=address, data_symbols=sorted(expected.intersection(symbols[address]))))
        result.append(dict(start=start, end=end, sha256=record['sha256'], source=record['source'],
                           first_line=record['first_line'], last_line=record['last_line'],
                           source_data_entries=entries, readers=[]))
    result.sort(key=lambda r: r['start'])
    if any(a['end'] > b['start'] for a, b in zip(result, result[1:])):
        raise ValueError('Overlapping source literal extents')
    dependency = root / 'runtime/tools/python-capstone'
    sys.path.insert(0, str(dependency))
    import capstone as cs
    from capstone import x86_const as x
    if not Path(cs._cs._name).resolve().is_relative_to(dependency.resolve()):
        raise ValueError('Expected pinned project-local instruction decoder')
    decoder = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_64)
    decoder.detail = True
    for line in disassembly.splitlines():
        match = re.match(r'^([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*)', line)
        if not match:
            continue
        address = int(match[1], 16)
        if any(r['start'] <= address < r['end'] for r in result):
            continue
        operand = match[3]
        branch = re.search(r'\b(?:callq?|jmpq?|j\w+|loop\w*)\s+(0x[0-9a-f]+)', operand)
        if branch and any(r['start'] <= int(branch[1], 16) < r['end'] for r in result):
            raise ValueError('Direct code branch enters source literal data')
        if '(%rip)' not in operand:
            continue
        encoded = bytes.fromhex(match[2])
        item = next(decoder.disasm(encoded, address, count=1), None)
        if item is None or item.size != len(encoded):
            raise ValueError('Cannot decode a potential source-literal reference')
        for op in item.operands:
            if op.type != x.X86_OP_MEM or op.mem.base != x.X86_REG_RIP:
                continue
            target = address + item.size + op.mem.disp
            region = next((r for r in result if r['start'] <= target < r['end']), None)
            if region is None:
                continue
            if item.mnemonic != 'lea' and (not op.access & cs.CS_AC_READ or op.access & cs.CS_AC_WRITE or target + op.size > region['end']):
                raise ValueError('Literal reference is not an in-bounds data read/address')
            if item.mnemonic in ('call', 'jmp'):
                raise ValueError('Indirect code branch uses source literal data')
            region['readers'].append(dict(instruction=address, target=target, operation=item.mnemonic))
    if any(not r['readers'] for r in result):
        raise ValueError('Source literal region has no native data reader')
    return result
