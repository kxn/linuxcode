"""Group extractor-appended N_INDR aliases without losing symbol indices.

Only the observed layout (locals, definitions, undefineds, appended aliases)
is supported. No symbol names, descriptors or alias targets are changed.
Unmodelled index-bearing side tables cause refusal rather than stale indices.
"""
import struct


def normalize(symbol_data, string_data, command, indirect_data):
    symbols = bytes(symbol_data)
    strings = bytes(string_data)
    dynamic = bytes(command)
    indirect = bytes(indirect_data)
    if len(symbols) % 16 or len(dynamic) != 80 or len(indirect) % 4:
        raise ValueError('Malformed symbol or dynamic-symbol table size')
    if struct.unpack_from('<II', dynamic) != (0xb, 80):
        raise ValueError('Not LC_DYSYMTAB')
    count = len(symbols)//16
    local, nlocal, defined, ndefined, undefined, nundefined = struct.unpack_from('<6I', dynamic, 8)
    if (local, defined, undefined) != (0, nlocal, nlocal+ndefined):
        raise ValueError('Noncontiguous existing dynamic-symbol groups')
    end = undefined+nundefined
    if end > count:
        raise ValueError('Dynamic-symbol groups exceed symbol table')
    if end == count:
        return bytearray(symbols), bytearray(dynamic), indirect, dict(repaired=False)
    fields = struct.unpack_from('<18I', dynamic, 8)
    if any(fields[i] for i in [6,7,8,9,10,11,14,15,16,17]):
        raise ValueError('Cannot remap nonempty index-bearing side tables')
    if fields[13] != len(indirect)//4:
        raise ValueError('Indirect symbol count differs from payload')

    def entry(index):
        return struct.unpack_from('<IBBHQ', symbols, index*16)

    def string(offset):
        if offset >= len(strings):
            raise ValueError('Symbol string offset outside table')
        try:
            stop = strings.index(0, offset)
            result = strings[offset:stop].decode('utf-8')
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError('Invalid symbol string') from error
        if not result:
            raise ValueError('Empty symbol or alias name')
        return result

    for i in range(nlocal):
        if entry(i)[1]&1:
            raise ValueError('External symbol in local group')
    for i in range(defined, undefined):
        kind = entry(i)[1]
        if not kind&1 or kind&0xe not in (2, 0xa, 0xe) or kind&0xe0:
            raise ValueError('Unexpected external-definition group')
    for i in range(undefined, end):
        _, kind, section, _, value = entry(i)
        if kind != 1 or section or value:
            raise ValueError('Unexpected undefined-symbol group')
    names = []
    renamed = []
    for i in range(end, count):
        offset, kind, section, desc, value = entry(i)
        if (kind, section, desc) != (0xb, 0, 0):
            raise ValueError('Only appended external N_INDR aliases are supported')
        name = string(offset)
        target = string(value)
        if target != name:
            renamed.append(dict(name=name, target=target))
        names.append(name)
    order = [*range(undefined), *range(end, count), *range(undefined, end)]
    assert len(order) == count and len(set(order)) == count
    inverse = {old: new for new, old in enumerate(order)}
    new_symbols = bytearray().join(symbols[i*16:(i+1)*16] for i in order)
    new_dynamic = bytearray(dynamic)
    struct.pack_into('<6I', new_dynamic, 8, 0, nlocal, defined,
        ndefined+count-end, undefined+count-end, nundefined)
    new_indirect = bytearray(indirect)
    changed = 0
    for i in range(len(indirect)//4):
        index = struct.unpack_from('<I', indirect, 4*i)[0]
        if index&0xc0000000:
            continue
        if index >= count:
            raise ValueError('Indirect symbol index outside symbol table')
        new_index = inverse[index]
        struct.pack_into('<I', new_indirect, 4*i, new_index)
        changed += new_index != index
    return new_symbols, new_dynamic, bytes(new_indirect), dict(repaired=True,
        original_symbol_count=count, original_groups=[local,nlocal,defined,ndefined,undefined,nundefined],
        new_groups=list(struct.unpack_from('<6I', new_dynamic, 8)),
        appended_external_aliases=count-end, alias_names=names,
        renamed_aliases_preserved=renamed,
        indirect_entries=len(indirect)//4, remapped_indirect_entries=changed,
        symbol_records_preserved=True, alias_targets_unchanged=True, symbol_indices_remapped=True)
