#!/usr/bin/env python3
"""Independently inspect serialized code bytes and eager/lazy patch bindings."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess


def macho(data):
    assert data[:4] == bytes.fromhex('cffaedfe')
    segments, sections, streams = [], {}, None
    cursor = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, length = struct.unpack_from('<II', data, cursor)
        assert length >= 8 and cursor + length <= len(data)
        if command == 0x19:
            name = data[cursor+8:cursor+24].rstrip(b'\0').decode()
            address, size, offset, file_size = struct.unpack_from('<4Q', data, cursor+24)
            segments.append((name, address, size, offset, file_size))
            for i in range(struct.unpack_from('<I', data, cursor+64)[0]):
                at = cursor + 72 + i*80
                section = data[at:at+16].rstrip(b'\0').decode()
                start, count, fileoff = struct.unpack_from('<QQI', data, at+32)
                flags = struct.unpack_from('<I', data, at+64)[0]
                sections[name, section] = (start, count, fileoff, flags)
        elif command == 0x80000022:
            streams = struct.unpack_from('<10I', data, cursor+8)
        cursor += length
    return segments, sections, streams


def binding_stream(data, lazy=False):
    cursor = 0
    state = dict(ordinal=0, symbol=None, weak=False, addend=0, segment=None, offset=0)
    result = {}

    def number(signed=False):
        nonlocal cursor
        value = shift = 0
        while True:
            byte = data[cursor]
            cursor += 1
            value |= (byte & 127) << shift
            shift += 7
            assert shift <= 70
            if byte < 128:
                if signed and byte & 64: value -= 1 << shift
                return value

    while cursor < len(data):
        byte = data[cursor]
        cursor += 1
        opcode, immediate = byte & 0xf0, byte & 15
        if opcode == 0:
            if not lazy:
                assert cursor == len(data)
                break
        elif opcode == 0x10: state['ordinal'] = immediate
        elif opcode == 0x20: state['ordinal'] = number()
        elif opcode == 0x30: state['ordinal'] = immediate if immediate == 0 else immediate - 16
        elif opcode == 0x40:
            end = data.index(0, cursor)
            state['symbol'] = data[cursor:end].decode()
            state['weak'] = bool(immediate & 1)
            cursor = end + 1
        elif opcode == 0x50: assert immediate == 1
        elif opcode == 0x60: state['addend'] = number(signed=True)
        elif opcode == 0x70:
            state['segment'] = immediate
            state['offset'] = number()
        elif opcode == 0x90:
            key = state['segment'], state['offset']
            assert key not in result and state['symbol'] is not None
            result[key] = (state['symbol'], state['ordinal'], state['weak'], state['addend'])
            state['offset'] += 8
        else: raise AssertionError('Unexpected classic binding opcode: ' + hex(byte))
    return result


def inspect(original, candidate, report):
    original_segments, original_sections, _ = macho(original)
    segments, sections, streams = macho(candidate)
    base = next(s[1] for s in original_segments if s[0] == '__TEXT')
    ordered = sorted(segments, key=lambda s: s[1])
    for first, second in zip(ordered, ordered[1:]):
        assert first[1] + first[2] <= second[1], 'Overlapping candidate segments'
    code = []
    for key, (address, size, offset, flags) in original_sections.items():
        if not flags & 0x80000400: continue
        target = address-base
        # The pinned builder merges code/stub/literal section descriptions to
        # fit the original header. Check their actual VM/file bytes rather
        # than assuming the old section names or boundaries survive.
        owner = [s for s in segments if s[1] <= target and target+size <= s[1]+s[4]]
        assert len(owner) == 1
        assert any(start <= target and target+size <= start+length and flags & 0x80000400
                   for start, length, _, flags in sections.values())
        target_offset = owner[0][3] + target-owner[0][1]
        before, after = original[offset:offset+size], candidate[target_offset:target_offset+size]
        assert len(before) == size and before == after, 'Original executable bytes differ'
        code.append(dict(segment=key[0], section=key[1], bytes=size,
            sha256=hashlib.sha256(before).hexdigest()))
    assert code and streams is not None
    actual = {}
    for label, i in [('eager', 2), ('lazy', 6)]:
        offset, size = streams[i:i+2]
        for (index, at), binding in binding_stream(candidate[offset:offset+size], label == 'lazy').items():
            segment = segments[index]
            assert at+8 <= segment[2], 'Binding outside segment'
            address = segment[1]+at
            assert address not in actual
            assert any(start <= address and address+8 <= start+size for start, size, _, _ in sections.values()), 'Binding outside section'
            actual[address] = binding
    got = report['byte_preserving_patch_got']['cells']
    addends = report['patch_metadata_addends']['bindings']
    for cell in [*got, *addends]:
        address = int(cell['slot'], 16)-base
        assert actual[address] == (cell['symbol'], cell['ordinal'], cell['weak'], cell['addend']), 'Serialized binding differs'
    assert report['rip_instructions_patched'] == 0
    return dict(executable_sections=code, original_code_bytes_equal=True,
        original_vm_offsets_preserved=True, got_cells_verified=len(got),
        nonzero_addends_verified=len(addends), serialized_bindings=len(actual),
        bindings_within_sections=True, runtime_behavior_verified=False,
        resource_compilation_verified=False)


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    pin_path = root / 'config/coregraphics-image-pins.json'
    pin = json.loads(pin_path.read_text())[args.target]
    original = root / ('runtime/fullsystem-libraries' + pin['path'])
    candidate = root / ('runtime/rebuilt-' + args.target) / Path(pin['path']).name
    report_path = candidate.with_name('reconstruction.json')
    report = json.loads(report_path.read_text())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest(original) == pin['sha256'] == report['original_image_sha256']
    assert digest(candidate) == report['staged_image_sha256']
    result = inspect(original.read_bytes(), candidate.read_bytes(), report)
    llvm = subprocess.run(['llvm-objdump-19', '--macho', '--bind', '--lazy-bind', str(candidate)],
        capture_output=True, text=True)
    assert llvm.returncode == 0, llvm.stderr
    result['llvm_bind_and_lazy_bind_tables_parsed'] = True
    result['llvm_binding_tables_sha256'] = hashlib.sha256(llvm.stdout.encode()).hexdigest()
    result['files'] = {str(p.relative_to(root)): digest(p) for p in [Path(__file__), pin_path,
        original, candidate, report_path]}
    result['verified'] = True
    output = root / args.output
    assert not output.exists()
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
