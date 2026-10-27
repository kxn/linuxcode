#!/usr/bin/env python3
"""Independent Mach-O ad-hoc page/special-slot/resource hash verifier.

This does not validate CMS, certificates, provisioning, requirements semantics,
nested code. It deliberately rejects unsupported slot layouts.
"""
from pathlib import Path
import hashlib, plistlib, re, struct

def verify(app, binary_data=None, *, cms_verifier=None):
    app = Path(app)
    info_data = (app / 'Info.plist').read_bytes()
    info = plistlib.loads(info_data)
    executable = info['CFBundleExecutable']
    binary = (app / executable).read_bytes() if binary_data is None else binary_data
    if binary[:4] == b'\xca\xfe\xba\xbe':
        count = struct.unpack_from('>I', binary, 4)[0]
        assert 0 < count <= 64 and 8 + 20 * count <= len(binary)
        ranges = []; slices = []
        for i in range(count):
            cpu, subtype, offset, size, align = struct.unpack_from('>5I', binary, 8 + 20 * i)
            assert size >= 32 and offset >= 8 + 20 * count and offset + size <= len(binary)
            assert align <= 31 and offset % (1 << align) == 0
            assert all(offset + size <= start or offset >= stop for start, stop in ranges)
            ranges.append((offset, offset + size))
            data = binary[offset:offset + size]
            assert data[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe'), 'little-endian Mach-O required'
            assert struct.unpack_from('<II', data, 4) == (cpu, subtype)
            slices.append(dict(cpu_type=cpu, cpu_subtype=subtype, offset=offset, size=size,
                               signature=verify(app, data, cms_verifier=cms_verifier)))
        return dict(verified=True, fat_slices=slices, certificate_or_device_trust_verified=False)
    magic = struct.unpack_from('<I', binary)[0]
    assert magic in (0xfeedfacf, 0xfeedface), 'little-endian Mach-O required'
    cursor = 32 if magic == 0xfeedfacf else 28
    signature = None
    for _ in range(struct.unpack_from('<I', binary, 16)[0]):
        command, length = struct.unpack_from('<II', binary, cursor)
        assert length >= 8 and cursor + length <= len(binary)
        if command == 0x1d:
            assert signature is None
            offset, size = struct.unpack_from('<II', binary, cursor + 8)
            assert offset + size <= len(binary)
            signature = binary[offset:offset + size]
            signature_offset = offset
        cursor += length
    assert signature is not None, 'missing code signature'
    magic, length, count = struct.unpack_from('>III', signature)
    assert magic == 0xfade0cc0 and 12 + count * 8 <= length <= len(signature)
    blobs = {}
    for i in range(count):
        slot, offset = struct.unpack_from('>II', signature, 12 + i * 8)
        assert slot not in blobs and offset >= 12 + count * 8 and offset + 8 <= length
        blob_length = struct.unpack_from('>I', signature, offset + 4)[0]
        assert blob_length >= 8 and offset + blob_length <= length
        blobs[slot] = signature[offset:offset + blob_length]
    cd = blobs[0]
    magic, length, version, flags, hash_offset, identifier, special, pages, limit = struct.unpack_from('>9I', cd)
    hash_size, hash_type, platform, page_exp = struct.unpack_from('>4B', cd, 36)
    assert magic == 0xfade0c02 and length == len(cd) and version <= 0x20600
    if cms_verifier is None: assert flags & 2, 'ad-hoc flag missing'
    else: assert not flags & 2, 'certificate signature unexpectedly marked ad-hoc'
    assert hash_type in [1, 2] and hash_size == {1: 20, 2: 32}[hash_type]
    assert page_exp in [12, 14] and limit == signature_offset
    algorithm = 'sha1' if hash_type == 1 else 'sha256'
    digest = lambda data: hashlib.new(algorithm, data).digest()
    assert hash_offset >= special * hash_size and hash_offset + pages * hash_size <= len(cd)
    assert pages == (limit + (1 << page_exp) - 1) >> page_exp
    for i in range(pages):
        actual = digest(binary[i << page_exp:min((i + 1) << page_exp, limit)])
        assert actual == cd[hash_offset + i * hash_size:hash_offset + (i + 1) * hash_size], 'code page hash mismatch'
    identifier_end = cd.index(0, identifier)
    assert cd[identifier:identifier_end].decode() == info['CFBundleIdentifier']
    resource_data = (app / '_CodeSignature/CodeResources').read_bytes()
    for slot in range(1, special + 1):
        stored = cd[hash_offset - slot * hash_size:hash_offset - (slot - 1) * hash_size]
        if stored == bytes(hash_size): continue
        if slot == 1: data = info_data
        elif slot == 3: data = resource_data
        else:
            assert slot in [2, 5, 7] and slot in blobs, 'unsupported special slot'
            data = blobs[slot]
        assert digest(data) == stored, 'special slot hash mismatch: ' + str(slot)
    # Apple emits an empty BlobWrapper for ad-hoc signatures. Only that exact
    # empty envelope is allowed; a nonempty CMS payload remains unsupported.
    cms = blobs.get(0x10000)
    cms_result = None
    if cms_verifier is None:
        assert cms is None or cms == struct.pack('>II', 0xfade0b01, 8), 'CMS is outside this verifier scope'
    else:
        assert cms and len(cms)>8 and struct.unpack_from('>II',cms)==(0xfade0b01,len(cms))
        cms_result = cms_verifier(cd,cms[8:],blobs)
        assert cms_result.get('verified') is True, 'CMS verification failed'
    resources = plistlib.loads(resource_data)
    checked = set()
    for table in ['files', 'files2']:
        for name, seal in resources.get(table, {}).items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            path = app / name
            assert path.is_file(), 'missing sealed resource: ' + name
            data = path.read_bytes()
            if isinstance(seal, bytes):
                assert hashlib.sha1(data).digest() == seal, 'resource SHA1 mismatch'
            else:
                assert set(seal) <= {'hash', 'hash2', 'optional'}, 'nested/symlink code outside scope'
                assert 'hash' in seal or 'hash2' in seal
                if 'hash' in seal: assert hashlib.sha1(data).digest() == seal['hash'], 'resource SHA1 mismatch'
                if 'hash2' in seal: assert hashlib.sha256(data).digest() == seal['hash2'], 'resource SHA256 mismatch'
            checked.add(name)
    for path in app.rglob('*'):
        if not path.is_file(): continue
        name = str(path.relative_to(app))
        if name == executable or name.startswith('_CodeSignature/'): continue
        applicable = []
        for pattern, rule in resources['rules2'].items():
            if re.search(pattern, name):
                applicable.append((rule.get('weight', 1) if isinstance(rule, dict) else 1,
                                   rule.get('omit', False) if isinstance(rule, dict) else False))
        assert applicable
        omitted = max(applicable, key=lambda item: item[0])[1]
        if not omitted: assert name in resources.get('files2', {}), 'unsealed added resource: ' + name
    result = dict(verified=True, code_pages=pages, special_slots=special, sealed_resources=len(checked),
                identifier=info['CFBundleIdentifier'], hash_algorithm=algorithm,
                certificate_or_device_trust_verified=False)
    if cms_result is not None: result['certificate_CMS']=cms_result
    return result

if __name__ == '__main__':
    import argparse, json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.app), indent=2))
