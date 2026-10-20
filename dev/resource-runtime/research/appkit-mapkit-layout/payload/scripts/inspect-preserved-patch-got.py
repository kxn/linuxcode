#!/usr/bin/env python3
"""Independently inspect serialized code bytes and eager/lazy patch bindings."""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import re
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


def binding_stream(data, lazy=False, segment_trace=None):
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
        opcode_at = cursor
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
            if segment_trace is not None:
                segment_trace.append(dict(opcode_offset=opcode_at,segment=immediate,offset=state['offset']))
        elif opcode == 0x90:
            key = state['segment'], state['offset']
            assert key not in result and state['symbol'] is not None
            result[key] = (state['symbol'], state['ordinal'], state['weak'], state['addend'])
            state['offset'] += 8
        else: raise AssertionError('Unexpected classic binding opcode: ' + hex(byte))
    return result


def rebase_stream(data):
    assert data and data[0] == 0x11
    cursor, result = 1, set()
    while cursor < len(data):
        opcode = data[cursor]
        cursor += 1
        if opcode == 0:
            assert cursor == len(data)
            return result
        assert opcode & 0xf0 == 0x20
        segment = opcode & 15
        offset = shift = 0
        while True:
            byte = data[cursor]
            cursor += 1
            offset |= (byte & 127) << shift
            shift += 7
            assert shift <= 70
            if byte < 128: break
        assert data[cursor] == 0x51
        cursor += 1
        assert (segment, offset) not in result
        result.add((segment, offset))
    raise AssertionError('Missing rebase stream terminator')


def inspect(original, candidate, report, original_cache_read=None):
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
    for row in report['byte_preserving_patch_got'].get('original_pooled_swift_any',[]):
        slot=int(row['slot'],16)-base
        assert actual[slot]==(row['symbol'],row['ordinal'],False,0), 'Swift Any pool binding differs'
        instruction=int(row['instruction'],16)-base
        owners=[s for s in segments if s[1]<=instruction and instruction+11<=s[1]+s[4]];assert len(owners)==1
        section=owners[0];off=section[3]+instruction-section[1]
        assert candidate[off:off+11]==bytes.fromhex(row['instruction_bytes'])
        if original_cache_read is not None:
            assert original_cache_read(int(row['slot'],16),8)==bytes.fromhex(row['original_encoded_slot'])
            assert original_cache_read(int(row['original_target'],16)+8,8)==struct.pack('<Q',row['metadata_kind'])
    indices=report['byte_preserving_patch_got'].get('original_pooled_enum_indices',[])
    if indices:
        assert all(s[1]%4096==s[3]%4096 for s in segments), 'Segment file/VM page offsets differ'
        serialized_rebases=rebase_stream(candidate[streams[0]:streams[0]+streams[1]])
        def locate(vm,size):
            matches=[(i,s) for i,s in enumerate(segments) if s[1]<=vm and vm+size<=s[1]+s[4]]
            assert len(matches)==1
            i,s=matches[0];return i,s,s[3]+vm-s[1]
        for row in indices:
            slot=int(row['slot'],16)-base;address=int(row['literal_address'],16)-base
            i,seg,off=locate(slot,8);assert (i,slot-seg[1]) in serialized_rebases and slot not in actual
            assert struct.unpack_from('<Q',candidate,off)[0]==address
            _,constant,off=locate(address,4);assert constant[0]=='__ENUM_LITERALS' and address%4==0
            payload=bytes.fromhex(row['literal_bytes']);assert len(payload)==4 and candidate[off:off+4]==payload
            cursor=32;found=False
            for _ in range(struct.unpack_from('<I',candidate,16)[0]):
                cmd,size=struct.unpack_from('<II',candidate,cursor)
                if cmd==0x19 and candidate[cursor+8:cursor+24].rstrip(b'\0')==b'__ENUM_LITERALS':
                    assert struct.unpack_from('<ii',candidate,cursor+56)==(1,1);found=True
                cursor+=size
            assert found
            pc=int(row['instruction'],16)-base;_,_,off=locate(pc,7)
            assert candidate[off:off+7]==bytes.fromhex(row['instruction_bytes'])
            if original_cache_read is not None:
                assert original_cache_read(int(row['slot'],16),8)==bytes.fromhex(row['original_encoded_slot'])
                assert original_cache_read(int(row['original_target'],16),4)==payload
    references = report['byte_preserving_patch_got'].get('address_references', [])
    local_cells = report['byte_preserving_patch_got'].get('original_local_stub_cells', [])
    null_pool_cells = report['byte_preserving_patch_got'].get('original_null_pool_cells', [])
    if references or null_pool_cells or any('local_target' in cell or cell.get('original_null') for cell in local_cells):
        offset, size = streams[:2]
        rebases = rebase_stream(candidate[offset:offset+size])
        cells = {int(cell['slot'], 16)-base: cell for cell in got}
        for reference in references:
            address, target = int(reference['slot'], 16)-base, int(reference['cell'], 16)-base
            owners = [(i, segment) for i, segment in enumerate(segments)
                      if segment[1] <= address and address+8 <= segment[1]+segment[2]]
            assert len(owners) == 1
            index, segment = owners[0]
            assert (index, address-segment[1]) in rebases, 'GOT address reference lacks a rebase'
            fileoff = segment[3]+address-segment[1]
            assert struct.unpack_from('<Q', candidate, fileoff)[0] == target, 'GOT address reference targets wrong cell'
            assert target in cells and reference['symbol'] == cells[target]['symbol']
    for cell in local_cells:
        address = int(cell['slot'],16)-base
        assert any(start<=int(cell['slot'],16) and int(cell['slot'],16)+8<=start+size and
                   (flags&255 in (6,7) or (key==('__DATA_CONST','__got') and flags==0))
                   for key,(start,size,_,flags) in original_sections.items())
        if cell.get('original_null'):
            original_address=int(cell['slot'],16)
            old_segment=next(segment for segment in original_segments
                if segment[1]<=original_address and original_address+8<=segment[1]+segment[2])
            old_offset=old_segment[3]+original_address-old_segment[1]
            assert original[old_offset:old_offset+8]==bytes(8),'Original NULL cell changed'
            index,segment=next((i,segment) for i,segment in enumerate(segments)
                if segment[1]<=address and address+8<=segment[1]+segment[2])
            fileoff=segment[3]+address-segment[1]
            assert candidate[fileoff:fileoff+8]==bytes(8),'Preserved NULL cell changed'
            assert address not in actual and (index,address-segment[1]) not in rebases
        elif 'local_target' not in cell:
            assert actual[address] == (cell['symbol'],cell['ordinal'],cell['weak'],cell['addend'])
        else:
            owners = [(i,segment) for i,segment in enumerate(segments)
                      if segment[1]<=address and address+8<=segment[1]+segment[2]]
            assert len(owners) == 1
            index,segment = owners[0]
            assert (index,address-segment[1]) in rebases
            fileoff = segment[3]+address-segment[1]
            assert struct.unpack_from('<Q',candidate,fileoff)[0] == int(cell['local_target'],16)-base
    if null_pool_cells:
        assert original_cache_read is not None,'Original cache bytes required for NULL pooled cells'
        assert report.get('original_absent_weak_dependencies')
        for cell in null_pool_cells:
            original_address=int(cell['slot'],16);address=original_address-base
            assert original_cache_read(original_address,8)==bytes(8),'Reference pool cell is not NULL'
            assert cell['stubs']
            for stub in cell['stubs']:
                stub=int(stub,16)
                owners=[(start,size,offset) for start,size,offset,flags in original_sections.values()
                        if flags&255==8 and start<=stub and stub+6<=start+size]
                assert len(owners)==1
                start,size,offset=owners[0];offset+=stub-start
                encoded=original[offset:offset+6]
                assert encoded[:2]==b'\xff\x25' and stub+6+struct.unpack_from('<i',encoded,2)[0]==original_address
            owners=[(i,segment) for i,segment in enumerate(segments)
                    if segment[0]=='__PATCH_GOT' and segment[1]<=address and address+8<=segment[1]+segment[2]]
            assert len(owners)==1
            index,segment=owners[0];offset=segment[3]+address-segment[1]
            assert candidate[offset:offset+8]==bytes(8),'Preserved NULL pool cell changed'
            assert address not in actual and (index,address-segment[1]) not in rebases
    optimized_tlv = report.get('optimized_tlv_restoration', [])
    if optimized_tlv:
        assert original_cache_read is not None, 'Original cache bytes required for optimized TLV descriptors'
        dependencies = []
        cursor = 32
        for _ in range(struct.unpack_from('<I', candidate, 16)[0]):
            command, length = struct.unpack_from('<II', candidate, cursor)
            if command in (0xc, 0x80000018, 0x8000001f, 0x80000023):
                start = cursor+struct.unpack_from('<I', candidate, cursor+8)[0]
                dependencies.append(candidate[start:candidate.index(0, start)].decode())
            cursor += length
        ordinal = dependencies.index('/usr/lib/libSystem.B.dylib')+1
        offset, size = streams[:2]
        tlv_rebases = rebase_stream(candidate[offset:offset+size])
        template = [(start, size, flags & 255) for start, size, _, flags in original_sections.values()
                    if flags & 255 in (0x11, 0x12) and size]
        template_start = min(start for start, _, _ in template)
        template_size = max(start+size for start, size, _ in template)-template_start
        for proof in optimized_tlv:
            slot = int(proof['slot'], 16)
            owners = [(start, size) for start, size, _, flags in original_sections.values()
                      if flags & 255 == 0x13 and start <= slot and slot+24 <= start+size]
            assert len(owners) == 1 and owners[0][1] % 24 == 0 and (slot-owners[0][0]) % 24 == 0
            raw = original_cache_read(slot, 24)
            assert raw.hex() == proof['raw_original_descriptor'], 'Original TLV bytes differ'
            key, variable_offset, delta, initial_size = struct.unpack('<IIiI', raw[8:])
            assert proof['cache_key'] == key and proof['variable_offset'] == variable_offset
            assert int(proof['template_start'], 16) == template_start and proof['template_size'] == template_size
            assert variable_offset < template_size and initial_size == template_size
            assert proof['template_delta'] == delta == (template_start-slot-16 if any(kind == 0x11 for _, _, kind in template) else 0)
            assert int(proof['optimized_entry'], 16) == int(proof['bootstrap'], 16)+8
            address = slot-base
            assert actual[address] == ('__tlv_bootstrap', ordinal, False, 0), 'TLV bootstrap must use the disk ABI'
            index, segment = next((i, seg) for i, seg in enumerate(segments)
                                  if seg[1] <= address and address+24 <= seg[1]+seg[4])
            fileoff = segment[3]+address-segment[1]
            assert struct.unpack_from('<3Q', candidate, fileoff) == (0, 0, variable_offset), 'Restored TLV descriptor differs'
            assert address+8 not in actual and address+16 not in actual
            assert not any((index, address+delta-segment[1]) in tlv_rebases for delta in (0, 8, 16))
    assert report['rip_instructions_patched'] == 0
    return dict(executable_sections=code, original_code_bytes_equal=True,
        original_vm_offsets_preserved=True, got_cells_verified=len(got),
        nonzero_addends_verified=len(addends), serialized_bindings=len(actual),
        got_address_references_verified=len(references),
        original_local_stub_cells_verified=len(local_cells),
        original_null_pool_cells_verified=len(null_pool_cells),
        optimized_TLV_descriptors_verified=len(optimized_tlv),
        bindings_within_sections=True, runtime_behavior_verified=False,
        resource_compilation_verified=False)


def first_section_offset_conflicts(data):
    """Find real binds whose valid LC_SEGMENT offset fails a section-derived base."""
    segments,sections,streams=macho(data)
    conflicts=[]
    for label,index in [('eager',2),('lazy',6)]:
        offset,size=streams[index:index+2]
        for (segment_index,relative),binding in binding_stream(data[offset:offset+size],label=='lazy').items():
            segment=segments[segment_index]
            own=[(start,size) for (seg,name),(start,size,_,_) in sections.items() if seg==segment[0] and size]
            assert any(start<=segment[1]+relative and segment[1]+relative+8<=start+size for start,size in own)
            if own and own[0][0]!=segment[1]:
                wrong=own[0][0]+relative
                if not any(start<=wrong and wrong+8<=start+size for start,size in own):
                    conflicts.append(dict(segment=segment[0],offset=hex(relative),
                        first_section_prefix=hex(own[0][0]-segment[1]),symbol=binding[0]))
    return conflicts


def first_section_error_proof(data, stderr):
    """Match the reported LLVM opcode to its precise section-base calculation.

    LLVM 19 BindRebaseSegInfo uses the first section's address as a segment
    base. A valid native LC_SEGMENT offset may consequently appear either
    outside all sections or within the last seven bytes of a section.
    """
    errors=re.findall(r'BIND_OPCODE_SET_SEGMENT_AND_OFFSET_ULEB bad offset, '
        r'(not in section|extends beyond section boundary) for opcode at: 0x([0-9a-fA-F]+)',stderr)
    assert len(errors)==1,'Unsupported LLVM diagnostic'
    reason,opcode=errors[0];opcode=int(opcode,16)
    segments,sections,streams=macho(data);groups=[]
    for (seg,name),(start,size,_,_) in sections.items():
        if not groups or groups[-1]['name']!=seg:
            groups.append(dict(name=seg,base=start,sections=[]))
        groups[-1]['sections'].append((start,size))
    proofs=[]
    for label,index in [('eager',2),('lazy',6)]:
        offset,size=streams[index:index+2];trace=[]
        bindings=binding_stream(data[offset:offset+size],label=='lazy',trace)
        for row in trace:
            if row['opcode_offset']!=opcode:continue
            si,relative=row['segment'],row['offset']
            assert (si,relative) in bindings
            assert si<len(segments) and si<len(groups)
            segment,group=segments[si],groups[si]
            assert group['name']==segment[0] and group['base']!=segment[1]
            actual=segment[1]+relative;wrong=group['base']+relative
            assert any(start<=actual and actual+8<=start+length for start,length in group['sections'])
            containing=next(((start,length) for start,length in group['sections'] if start<=wrong<start+length),None)
            predicted='not in section' if containing is None else (
                'extends beyond section boundary' if wrong+8>sum(containing) else None)
            if predicted!=reason:continue
            proofs.append(dict(stream=label,opcode_offset=hex(opcode),segment=segment[0],
                offset=hex(relative),actual_address=hex(actual),LLVM_section_base_address=hex(wrong),
                reported_error=reason,symbol=bindings[si,relative][0]))
    assert proofs,'Reported LLVM opcode is not the independently verified first-section base limitation'
    return proofs


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--original-validator-report',
        help='Require matching original Apple positive and corruption controls for a known LLVM first-section offset failure')
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
    cache_read=None
    if report['byte_preserving_patch_got'].get('original_null_pool_cells') or report['byte_preserving_patch_got'].get('original_pooled_enum_indices') or report['byte_preserving_patch_got'].get('original_pooled_swift_any') or report.get('optimized_tlv_restoration'):
        ns=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
            'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
            'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
        if report['byte_preserving_patch_got'].get('original_null_pool_cells'):
            proof=runpy.run_path(str(root/'scripts/absent-weak-imports.py'))['audit'](
                original.read_bytes(),root/'runtime/fullsystem-libraries',ns['image'])
            assert proof==report['original_absent_weak_dependencies']
        cache_read=ns['read']
    if report['byte_preserving_patch_got'].get('original_pooled_swift_any'):
        validator='scripts/original-pooled-swift-any.py'
        expected=runpy.run_path(str(root/validator))['validate'](ns,pin['path'],pin['original_pooled_swift_any'])
        assert expected==report['byte_preserving_patch_got']['original_pooled_swift_any']
    if report['byte_preserving_patch_got'].get('original_pooled_enum_indices'):
        validator='scripts/original-pooled-enum-index.py'
        expected=runpy.run_path(str(root/validator))['validate'](ns,pin['path'],pin['original_pooled_enum_indices'])
        rows=report['byte_preserving_patch_got']['original_pooled_enum_indices']
        assert [{k:v for k,v in row.items() if k!='literal_address'} for row in rows]==expected
    result = inspect(original.read_bytes(), candidate.read_bytes(), report,cache_read)
    if report.get('dysymtab_alias_repair',{}).get('repaired'):
        verifier='scripts/verify-dysymtab-alias-repair.py'
        result['dysymtab_alias_repair']=runpy.run_path(str(root/verifier))['verify'](
            original.read_bytes(),candidate.read_bytes())
        result['dysymtab_alias_verifier']=dict(source=verifier,sha256=digest(root/verifier))
    llvm = subprocess.run(['llvm-objdump-19', '--macho', '--bind', '--lazy-bind', str(candidate)],
        capture_output=True, text=True)
    result['llvm_bind_and_lazy_bind_tables_parsed'] = llvm.returncode==0
    if llvm.returncode:
        assert args.original_validator_report, llvm.stderr
        opcode_proof=first_section_error_proof(candidate.read_bytes(),llvm.stderr)
        conflicts=first_section_offset_conflicts(candidate.read_bytes())
        assert conflicts,'LLVM failure does not match the first-section base limitation'
        validation_path=root/args.original_validator_report
        validation=json.loads(validation_path.read_text())
        assert validation['verified'] and validation['format_validation_only']
        assert validation['image']==str(candidate.relative_to(root))
        assert validation['image_sha256']==digest(candidate)
        assert validation['reference_image_sha256']==digest(original)
        assert validation['cases']==[['valid','0'],['bad-header','1'],['bad-binding','1']]
        assert validation['original_tool_bytes_equal_extracted'] and validation['outer_status']==0
        tool=root/'runtime/state/prefix'/validation['tool'].lstrip('/')
        expected_tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/dyld_info'
        assert validation['tool']==expected_tool
        extracted=root/'runtime/xcode-extract/Xcode.app'/expected_tool.split('/Applications/Xcode.app/',1)[1]
        assert digest(tool)==validation['tool_sha256']==digest(extracted)
        assert digest(root/validation['log'])==validation['log_sha256']
        result['LLVM_first_section_base_limitation']=dict(conflicting_valid_bindings=len(conflicts),
            examples=conflicts[:8],stderr=llvm.stderr,original_validator=args.original_validator_report,
            reported_opcode_proof=opcode_proof,
            original_validator_sha256=digest(validation_path),original_Apple_validation_verified=True)
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
