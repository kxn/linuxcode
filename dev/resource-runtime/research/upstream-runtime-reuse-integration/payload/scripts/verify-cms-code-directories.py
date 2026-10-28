#!/usr/bin/env python3
"""Bind every CodeDirectory to CMS signed attributes after OpenSSL verification.

Definite lengths and constructed BER indefinite lengths, a single SignerInfo
and Apple's original v1/v2 hash-agility layout are supported. The caller must first verify the CMS
signature against the primary CodeDirectory and the exact supplied certificate.
"""
import hashlib
import plistlib


def element(data, offset, depth=0):
    assert depth < 32 and offset + 2 <= len(data)
    tag, size = data[offset:offset + 2]; offset += 2
    assert tag and tag & 31 != 31, 'unexpected EOC or high ASN.1 tag'
    if size == 0x80:
        assert tag & 0x20, 'primitive indefinite length outside scope'
        start = offset
        while True:
            assert offset + 2 <= len(data)
            if data[offset:offset + 2] == b'\0\0': return tag, data[start:offset], offset + 2
            _, _, offset = element(data, offset, depth + 1)
    if size & 128:
        n = size & 127; assert 0 < n <= 4 and offset + n <= len(data)
        assert data[offset] != 0
        size = int.from_bytes(data[offset:offset + n], 'big'); offset += n
        assert size >= 128
    assert offset + size <= len(data)
    return tag, data[offset:offset + size], offset + size


def children(data):
    assert len(data) <= 16 * 1024 * 1024
    result = []; offset = 0
    while offset < len(data):
        tag, value, offset = element(data, offset)
        result.append((tag, value))
    return result


def sequence(data, tag=0x30):
    rows = children(data); assert len(rows) == 1 and rows[0][0] == tag
    return children(rows[0][1])


def verify_binding(cms, blobs):
    content = sequence(cms)
    assert len(content) == 2 and content[0] == (6, bytes.fromhex('2a864886f70d010702')) and content[1][0] == 0xa0
    signed = sequence(content[1][1]); assert signed[-1][0] == 0x31
    signers = children(signed[-1][1]); assert len(signers) == 1 and signers[0][0] == 0x30
    signer = children(signers[0][1]); assert len(signer) >= 6 and signer[3][0] == 0xa0
    attributes = {}
    for tag, data in children(signer[3][1]):
        assert tag == 0x30
        row = children(data); assert len(row) == 2 and row[0][0] == 6 and row[1][0] == 0x31
        oid = row[0][1]; assert oid not in attributes
        attributes[oid] = children(row[1][1])
    v1 = attributes[bytes.fromhex('2a864886f763640901')]
    assert len(v1) == 1 and v1[0][0] == 4
    plist = plistlib.loads(v1[0][1]); assert set(plist) == {'cdhashes'}
    expected = []; full = []; slots = []
    algorithms = {1: ('sha1', bytes.fromhex('2b0e03021a')),
                  2: ('sha256', bytes.fromhex('608648016503040201'))}
    for slot, cd in sorted(blobs.items()):
        if cd[:4] != bytes.fromhex('fade0c02'): continue
        assert slot == 0 or 0x1000 <= slot < 0x1006
        assert len(cd) >= 44
        algorithm, oid = algorithms[cd[37]]
        digest = hashlib.new(algorithm, cd).digest()
        expected.append(digest[:20]); full.append((oid, digest)); slots.append(slot)
    assert slots and slots[0] == 0
    assert len(plist['cdhashes']) == len(expected) and sorted(plist['cdhashes']) == sorted(expected), 'CMS v1 does not bind all CodeDirectories'
    actual = []
    for tag, data in attributes[bytes.fromhex('2a864886f763640902')]:
        assert tag == 0x30
        row = children(data); assert len(row) == 2 and row[0][0] == 6 and row[1][0] == 4
        actual.append((row[0][1], row[1][1]))
    assert sorted(actual) == sorted(full), 'CMS v2 does not bind all CodeDirectories'
    return dict(bound_CodeDirectory_slots=slots, Apple_signed_hash_agility_v1_verified=True,
                Apple_signed_hash_agility_v2_verified=True)
