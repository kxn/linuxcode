#!/usr/bin/env python3
"""Prepare hash-pinned local Darling startup guards in complete Mach-O images.

Only a named-sandbox startup call is replaced by a forward jump to an audited
continuation. No API return value or shared library is changed. Outputs retain
their now-invalid original signatures and MUST NOT be installed until separately
ad-hoc signed and independently verified. This tool never invokes native code.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, os, plistlib, re, struct, subprocess, tempfile

ROOT = Path(__file__).resolve().parent.parent
sha = lambda b: hashlib.sha256(b).hexdigest()


def local_file(name):
    spelling = PurePosixPath(name)
    assert not spelling.is_absolute() and '..' not in spelling.parts
    p = (ROOT / name).resolve(strict=True)
    assert p.is_relative_to(ROOT) and p.is_file()
    return p


def slices(data):
    if data[:4] == bytes.fromhex('cafebabe'):
        count = struct.unpack_from('>I', data, 4)[0]
        assert 0 < count < 32 and 8 + count * 20 <= len(data)
        rows = [struct.unpack_from('>5I', data, 8 + i * 20)[:4] for i in range(count)]
    else:
        assert data[:4] == bytes.fromhex('cffaedfe')
        rows = [(*struct.unpack_from('<II', data, 4), 0, len(data))]
    ranges = []
    for cpu, subtype, offset, size in rows:
        assert size >= 32 and 0 <= offset <= len(data) - size
        assert all(offset >= hi or offset + size <= lo for lo, hi in ranges)
        ranges.append((offset, offset + size))
        binary = data[offset:offset + size]
        assert binary[:4] == bytes.fromhex('cffaedfe')
        assert struct.unpack_from('<II', binary, 4) == (cpu, subtype)
        yield dict(cpu_type=cpu, cpu_subtype=subtype, slice_offset=offset,
                   slice_size=size, data=binary)


def commands(binary):
    at = 32
    count, total = struct.unpack_from('<II', binary, 16)
    assert total <= len(binary) - at
    for _ in range(count):
        kind, size = struct.unpack_from('<II', binary, at)
        assert size >= 8 and at + size <= 32 + total
        yield kind, at, size
        at += size
    assert at == 32 + total


def sections(binary):
    for kind, at, size in commands(binary):
        if kind != 0x19:
            continue
        count = struct.unpack_from('<I', binary, at + 64)[0]
        assert 72 + count * 80 <= size
        for i in range(count):
            pos = at + 72 + i * 80
            name = binary[pos:pos + 16].split(b'\0')[0].decode()
            segment = binary[pos + 16:pos + 32].split(b'\0')[0].decode()
            vm, length, file_offset = struct.unpack_from('<QQI', binary, pos + 32)
            yield segment, name, vm, length, file_offset


def code_offset(binary, vm, length=1):
    for segment, name, start, size, offset in sections(binary):
        if segment == '__TEXT' and name == '__text' and start <= vm and vm + length <= start + size:
            assert offset + vm - start + length <= len(binary)
            return offset + vm - start
    raise ValueError('Guard address is outside executable __TEXT,__text')


def signature_metadata(binary):
    matches = [(at, size) for kind, at, size in commands(binary) if kind == 0x1d]
    assert len(matches) == 1
    offset, capacity = struct.unpack_from('<II', binary, matches[0][0] + 8)
    assert offset <= len(binary) and capacity <= len(binary) - offset
    signature = binary[offset:offset + capacity]
    magic, size, count = struct.unpack_from('>III', signature)
    assert magic == 0xfade0cc0 and 12 + count * 8 <= size <= capacity
    blobs = {}
    for i in range(count):
        slot, pos = struct.unpack_from('>II', signature, 12 + i * 8)
        assert slot not in blobs and pos >= 12 + count * 8 and pos + 8 <= size
        length = struct.unpack_from('>I', signature, pos + 4)[0]
        assert 8 <= length <= size - pos
        blobs[slot] = signature[pos:pos + length]
    cd = blobs[0]
    magic, size, version, flags = struct.unpack_from('>4I', cd)
    assert magic == 0xfade0c02 and size == len(cd) and version <= 0x20600
    ident = struct.unpack_from('>I', cd, 20)[0]
    assert 44 <= ident < len(cd)
    identifier = cd[ident:cd.index(0, ident)].decode()
    runtime = struct.unpack_from('>I', cd, 88)[0] if version >= 0x20500 else None
    xml = blobs.get(5)
    der = blobs.get(7)
    if xml:
        assert struct.unpack_from('>II', xml) == (0xfade7171, len(xml))
        values = plistlib.loads(xml[8:])
        assert isinstance(values, dict)
    else:
        values = None
    if der:
        assert struct.unpack_from('>II', der) == (0xfade7172, len(der))
    return dict(identifier=identifier, code_directory_version=version,
                code_directory_flags=flags, code_directory_runtime=runtime,
                code_directory_platform=cd[38], signature_offset=offset,
                signature_capacity=capacity, xml=xml, der=der,
                entitlement_values=values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--outdir', help='New project-local runtime directory; must not exist')
    args = parser.parse_args()
    manifest_path = local_file(args.manifest)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest['scope'] == 'darling-named-sandbox-startup-platform-guard'
    assert manifest['shared_sandbox_API_unchanged'] is True
    assert manifest['trust_and_license_logic_unchanged'] is True
    inputs = []
    seen = set()
    for row in manifest['images']:
        assert re.fullmatch(r'[a-zA-Z0-9_-]+', row['name']) and row['name'] not in seen
        seen.add(row['name'])
        source = local_file(row['input'])
        data = source.read_bytes()
        assert sha(data) == row['input_sha256'], 'Different complete original image SHA256'
        for proof in row['source_proofs']:
            assert sha(local_file(proof['path']).read_bytes()) == proof['sha256']
        architectures = list(slices(data))
        for arch in architectures:
            arch['metadata'] = signature_metadata(arch['data'])
        x86 = [s for s in architectures if s['cpu_type'] == 0x1000007]
        assert len(x86) == 1
        x86 = x86[0]
        assert x86['slice_offset'] == row['x86_slice_offset']
        assert x86['cpu_subtype'] == row['x86_cpu_subtype']
        assert x86['metadata']['xml'], 'An actual original XML entitlement payload is required'
        canonical_entitlements = lambda value: plistlib.dumps(value, fmt=plistlib.FMT_BINARY, sort_keys=True)
        assert all(canonical_entitlements(s['metadata']['entitlement_values']) == canonical_entitlements(x86['metadata']['entitlement_values']) for s in architectures), 'Per-architecture entitlement semantics differ; prepare an explicitly Intel-only build instead'
        original = bytes.fromhex(row['original_five_bytes'])
        assert len(original) == 5 and original[0] == 0xe8
        site, target = int(row['site_vm'], 0), int(row['target_vm'], 0)
        assert site + 5 < target <= site + 256
        offset = code_offset(x86['data'], site, 5)
        target_offset = code_offset(x86['data'], target, 16)
        assert x86['data'][offset:offset + 5] == original, 'Different startup call bytes'
        assert sha(x86['data'][target_offset:target_offset + 16]) == row['target_16_bytes_sha256']
        disasm_command = ['llvm-objdump-19', '--macho', '--arch=x86_64', '--disassemble',
                          '--no-show-raw-insn', str(source)]
        disassembly = subprocess.check_output(disasm_command, text=True)
        lines = disassembly.splitlines()
        index = next(i for i, text in enumerate(lines) if text.startswith(f'{site:x}:'))
        assert 'symbol stub for: _sandbox_init_with_parameters' in lines[index]
        assert any(f'"{row["profile"]}"' in text for text in lines[max(0, index - 16):index])
        target_line = next(text for text in lines if text.startswith(f'{target:x}:'))
        assert row['target_asm_contains'] in target_line
        new_instruction = b'\xe9' + struct.pack('<i', target - site - 5)
        patched = bytearray(data)
        absolute = x86['slice_offset'] + offset
        patched[absolute:absolute + 5] = new_instruction
        assert patched[:absolute] == data[:absolute] and patched[absolute + 5:] == data[absolute + 5:]
        inputs.append((row, source, data, bytes(patched), architectures,
                       absolute, new_instruction, disasm_command, disassembly))
    # All fail-closed input/source/control-flow checks precede output creation.
    if args.outdir:
        spelling = PurePosixPath(args.outdir)
        assert not spelling.is_absolute() and '..' not in spelling.parts
        out = (ROOT / args.outdir).resolve()
        assert out.is_relative_to(ROOT / 'runtime') and not out.exists()
        out.mkdir()
    else:
        out = Path(tempfile.mkdtemp(prefix='darling-security-platform-guards-', dir=ROOT / 'runtime'))
    out.chmod(0o755)
    images = []
    for row, source, data, patched, architectures, offset, instruction, command, disassembly in inputs:
        folder = out / row['name']; folder.mkdir(mode=0o755)
        output = folder / row['name']; output.write_bytes(patched); output.chmod(0o755)
        (folder / 'original-disassembly.log').write_text(disassembly)
        entitlements = []
        for arch in architectures:
            meta = arch['metadata']
            stem = f'{arch["cpu_type"]:x}-{arch["cpu_subtype"]:x}'
            record = {k: v for k, v in arch.items() if k not in ['data', 'metadata']}
            record.update({k: v for k, v in meta.items() if k not in ['xml', 'der', 'entitlement_values']})
            for kind, extension in [('xml', 'plist'), ('der', 'der')]:
                blob = meta[kind]
                record[kind + '_payload'] = record[kind + '_sha256'] = None
                record[kind + '_blob'] = record[kind + '_blob_sha256'] = None
                if blob:
                    payload = folder / f'original-{stem}-entitlements.{extension}'
                    raw_blob = folder / f'original-{stem}-entitlements.{extension}.blob'
                    payload.write_bytes(blob[8:]); raw_blob.write_bytes(blob)
                    record[kind + '_payload'] = str(payload.relative_to(ROOT))
                    record[kind + '_sha256'] = sha(blob[8:])
                    record[kind + '_blob'] = str(raw_blob.relative_to(ROOT))
                    record[kind + '_blob_sha256'] = sha(blob)
            record['entitlement_keys'] = sorted((meta['entitlement_values'] or {}).keys())
            record['entitlement_values'] = meta['entitlement_values']
            entitlements.append(record)
        x86 = next(e for e in entitlements if e['cpu_type'] == 0x1000007)
        assert x86['xml_payload'], 'An actual original XML entitlement payload is required'
        assert all(canonical_entitlements(e['entitlement_values']) == canonical_entitlements(x86['entitlement_values']) for e in entitlements), 'Per-architecture entitlement semantics differ; do not sign with one plist'
        images.append(dict(name=row['name'], input=str(source.relative_to(ROOT)),
                           input_sha256=sha(data), output=str(output.relative_to(ROOT)),
                           patched_sha256=sha(patched), expected_identifier=x86['identifier'],
                           signing_entitlements=x86['xml_payload'],
                           original_entitlements=entitlements,
                           guard=dict(file_offset=offset, site_vm=row['site_vm'],
                                      target_vm=row['target_vm'], before=row['original_five_bytes'],
                                      after=instruction.hex(), text_bytes_replaced=5,
                                      all_other_bytes_identical=True),
                           disassembly_command=command,
                           state='invalid-signature-not-installed'))
    result = dict(host_verified=True, installed=False, native_executed=False,
                  state='invalid-signature-not-installed', local_Darling_compatibility_build=True,
                  Apple_signature_valid=False, macOS_named_sandbox_enforcement=False,
                  shared_sandbox_API_unchanged=True, trust_and_license_logic_unchanged=True,
                  input_manifest=str(manifest_path.relative_to(ROOT)),
                  input_manifest_sha256=sha(manifest_bytes), images=images,
                  script_sha256=sha(Path(__file__).read_bytes()),
                  publication_scope='Own source and audit metadata only; original/patched Apple binaries, raw disassembly and original signature blobs remain private runtime inputs.')
    (out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(out.relative_to(ROOT) / 'build.json')


if __name__ == '__main__':
    main()
