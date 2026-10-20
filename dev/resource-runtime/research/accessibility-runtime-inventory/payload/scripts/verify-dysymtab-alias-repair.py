"""Independently verify nlist grouping and every indirect symbol's identity."""
import hashlib
import struct


def tables(data):
    if data[:8] != bytes.fromhex('cffaedfe07000001'):
        raise AssertionError('Expected x86_64 Mach-O')
    at, sections, base, symbols, dynamic = 32, 0, None, None, None
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        cmd, size = struct.unpack_from('<II', data, at)
        assert size >= 8 and at+size <= len(data)
        if cmd == 0x19:
            sections += struct.unpack_from('<I', data, at+64)[0]
            if data[at+8:at+24].rstrip(b'\0') == b'__TEXT':
                base = struct.unpack_from('<Q', data, at+24)[0]
        elif cmd == 2:
            assert symbols is None
            symbols = struct.unpack_from('<4I', data, at+8)
        elif cmd == 0xb:
            assert dynamic is None and size == 80
            dynamic = struct.unpack_from('<18I', data, at+8)
        at += size
    assert base is not None and symbols is not None and dynamic is not None
    off, count, string_off, string_size = symbols
    assert off+count*16 <= len(data) and string_off+string_size <= len(data)
    strings = data[string_off:string_off+string_size]
    records = [struct.unpack_from('<IBBHQ', data, off+16*i) for i in range(count)]
    names = []
    for record in records:
        assert record[0] < len(strings)
        names.append(strings[record[0]:strings.index(0, record[0])].decode('utf-8'))
    indirect_off, indirect_count = dynamic[12:14]
    assert indirect_off+4*indirect_count <= len(data)
    indirect = list(struct.unpack_from('<'+str(indirect_count)+'I', data, indirect_off))
    return dict(records=records, names=names, strings=strings, dynamic=dynamic,
        indirect=indirect, base=base, sections=sections)


def verify(original, candidate):
    before, after = tables(original), tables(candidate)
    assert before['strings'] == after['strings']
    assert len(before['records']) == len(after['records'])

    def category(record):
        kind = record[1]
        if not kind&1:
            return 0
        return 2 if kind&0xe == 0 else 1

    # Derive a stable partition from actual nlist types, not the normalizer's
    # count arithmetic or its claimed old/new index mapping.
    order = sorted(range(len(before['records'])), key=lambda i: category(before['records'][i]))
    groups = [sum(category(r)==i for r in before['records']) for i in range(3)]
    assert list(after['dynamic'][:6]) == [0,groups[0],groups[0],groups[1],sum(groups[:2]),groups[2]]
    assert before['base'] >= after['base'] == 0
    aliases = 0
    renamed = []
    for new, old in enumerate(order):
        a, b = before['records'][old], after['records'][new]
        assert before['names'][old] == after['names'][new] and a[:2] == b[:2]
        assert a[3] == b[3], 'Symbol descriptor changed'
        if a[1]&0xe == 0xe:
            assert 0 < a[2] <= before['sections'] and 0 < b[2] <= after['sections']
            assert b[4] == a[4]-before['base'], 'Defined symbol address changed'
        else:
            assert a == b, 'Alias/undefined/absolute nlist bytes changed'
        if a[1] == 0xb:
            aliases += 1
            assert a[4] < len(before['strings'])
            target = before['strings'][a[4]:before['strings'].index(0, a[4])].decode('utf-8')
            assert target, 'Empty original alias target'
            # N_INDR n_value is a string-table offset, not an address.
            # Entire nlist and string tables were compared above; preserve
            # renamed reexports as well as extractor self-name aliases.
            if target != before['names'][old]:
                renamed.append(dict(name=before['names'][old], target=target))
    assert len(before['indirect']) == len(after['indirect'])
    inverse = {old:new for new,old in enumerate(order)}
    remapped = 0
    for a,b in zip(before['indirect'], after['indirect']):
        if a&0xc0000000:
            assert a == b, 'Special indirect symbol marker changed'
        else:
            assert a in inverse and b == inverse[a], 'Indirect symbol index not remapped'
            assert before['names'][a] == after['names'][b], 'Indirect symbol identity changed'
            remapped += a != b
    return dict(verified=True, symbol_count=len(order), actual_type_groups=groups,
        external_aliases=aliases, renamed_aliases_preserved=renamed,
        symbol_names_descriptors_and_alias_targets_preserved=True,
        defined_addresses_normalized=True, indirect_entries=len(before['indirect']),
        remapped_indirect_entries=remapped,
        original_sha256=hashlib.sha256(original).hexdigest(), candidate_sha256=hashlib.sha256(candidate).hexdigest())
