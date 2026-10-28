#!/usr/bin/env python3
"""Host-only verification of locally ad-hoc signed compatibility service copies.

Reuse the independent page/special-slot verifier and both existing entitlement
DER decoders. Compare metadata to the original binary; never treat a modified
service as retaining Apple's signature or platform identity.
"""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import runpy
import struct

ROOT = Path(__file__).resolve().parent.parent
VERIFIERS = [
    "scripts/verify-adhoc-macho-file.py",
    "scripts/verify-entitlements-der.py",
    "scripts/verify-apple-legacy-entitlements.py",
]
verify_adhoc = runpy.run_path(str(ROOT / VERIFIERS[0]))["verify"]
decode_ce = runpy.run_path(str(ROOT / VERIFIERS[1]))["decode"]
decode_legacy = runpy.run_path(str(ROOT / VERIFIERS[2]))["decode"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def semantic(value):
    """Type-sensitive plist equality (Python otherwise equates true and 1)."""
    if isinstance(value, dict):
        assert all(type(key) is str for key in value)
        return ("dict", tuple((key, semantic(item)) for key, item in sorted(value.items())))
    if isinstance(value, list):
        return ("array", tuple(semantic(item) for item in value))
    assert type(value) in (bool, int, str, bytes), "Unsupported entitlement plist value"
    return (type(value).__name__, value)


def metadata(path):
    """Extract only signature metadata; cryptographic checks stay in the verifier."""
    data = Path(path).read_bytes()
    slices = [(0, len(data))]
    if data[:4] == bytes.fromhex("cafebabe"):
        count = struct.unpack_from(">I", data, 4)[0]
        assert 0 < count < 32 and 8 + 20 * count <= len(data)
        slices = [struct.unpack_from(">IIIII", data, 8 + 20 * index)[2:4] for index in range(count)]
    result, occupied = {}, []
    for base, length in slices:
        assert length >= 32 and base <= len(data) and length <= len(data) - base
        assert all(base + length <= start or base >= stop for start, stop in occupied)
        occupied.append((base, base + length))
        binary = data[base:base + length]
        assert binary[:4] == bytes.fromhex("cffaedfe"), "Expected a little-endian 64-bit Mach-O"
        cpu, subtype, _, count, command_bytes = struct.unpack_from("<5I", binary, 4)
        assert (cpu, subtype) not in result and 32 + command_bytes <= length
        at, signature = 32, None
        for _ in range(count):
            command, size = struct.unpack_from("<II", binary, at)
            assert size >= 8 and at + size <= 32 + command_bytes
            if command == 29:
                assert signature is None and size >= 16
                offset, size2 = struct.unpack_from("<II", binary, at + 8)
                assert offset <= length and 12 <= size2 <= length - offset
                signature = binary[offset:offset + size2]
            at += size
        assert at == 32 + command_bytes and signature is not None
        magic, size, count = struct.unpack_from(">III", signature)
        assert magic == 0xfade0cc0 and 12 + 8 * count <= size <= len(signature)
        blobs, ranges = {}, []
        for index in range(count):
            slot, offset = struct.unpack_from(">II", signature, 12 + 8 * index)
            assert slot not in blobs and offset >= 12 + 8 * count and offset + 8 <= size
            blob_size = struct.unpack_from(">I", signature, offset + 4)[0]
            assert 8 <= blob_size <= size - offset
            assert all(offset + blob_size <= start or offset >= stop for start, stop in ranges)
            ranges.append((offset, offset + blob_size))
            blobs[slot] = signature[offset:offset + blob_size]
        assert 0 in blobs
        directories = []
        for slot, blob in sorted(blobs.items()):
            if slot != 0 and not 4096 <= slot < 4101:
                continue
            assert len(blob) >= 44 and struct.unpack_from(">II", blob) == (0xfade0c02, len(blob))
            flags, ident = struct.unpack_from(">I", blob, 12)[0], struct.unpack_from(">I", blob, 20)[0]
            assert 44 <= ident < len(blob)
            identifier = blob[ident:blob.index(0, ident)].decode("utf-8")
            assert identifier
            directories.append(dict(slot=slot, identifier=identifier, flags=flags))
        assert directories and len({item["identifier"] for item in directories}) == 1
        entitlements, formats, hashes = None, [], {}
        for slot, expected_magic, label in [(5, 0xfade7171, "XML"), (7, 0xfade7172, "DER")]:
            if slot not in blobs:
                continue
            blob = blobs[slot]
            assert struct.unpack_from(">II", blob) == (expected_magic, len(blob))
            payload = blob[8:]
            if slot == 5:
                value = plistlib.loads(payload)
            elif payload[:1] == b"\x70":
                value = decode_ce(payload)
            elif payload[:1] == b"\x31":
                value = decode_legacy(payload)
            else:
                raise ValueError("Unsupported entitlement DER envelope")
            assert type(value) is dict
            current = semantic(value)
            if entitlements is not None:
                assert entitlements == current, "XML and DER entitlement semantics differ"
            entitlements = current
            formats.append(label)
            hashes[label] = hashlib.sha256(payload).hexdigest()
        cms = blobs.get(65536)
        result[(cpu, subtype)] = dict(
            cpu_type=cpu, cpu_subtype=subtype, slice_offset=base,
            directories=directories, entitlement_semantic=entitlements,
            entitlement_formats=formats, entitlement_payload_sha256=hashes,
            cms_payload_present=cms not in (None, b"", bytes.fromhex("fade0b0100000008")),
        )
    return result


def verify_pair(original, signed, expected_identifier=None):
    original, signed = Path(original), Path(signed)
    before = {str(path): sha(path) for path in [original, signed]}
    independent = verify_adhoc(signed)
    assert independent["verified"] and independent["ad_hoc_only"]
    old, new = metadata(original), metadata(signed)
    assert any(cpu == 0x1000007 for cpu, _ in new), "Intel slice required"
    rows = []
    for architecture, current in new.items():
        assert architecture in old, "New or altered CPU/subtype"
        source = old[architecture]
        label = source["directories"][0]["identifier"]
        if expected_identifier is not None:
            assert label == expected_identifier, "Guard manifest identifier differs from original"
        assert all(item["identifier"] == label and item["flags"] & 2 for item in current["directories"]), "Identifier or ad-hoc flag changed"
        assert not current["cms_payload_present"], "Nonempty CMS survived local ad-hoc signing"
        assert current["entitlement_semantic"] == source["entitlement_semantic"], "Original entitlement semantics were changed or dropped"
        assert set(source["entitlement_formats"]) <= set(current["entitlement_formats"]), "Original XML or DER entitlement representation was dropped"
        rows.append(dict(
            cpu_type=architecture[0], cpu_subtype=architecture[1], identifier=label,
            original_entitlement_formats=source["entitlement_formats"], signed_entitlement_formats=current["entitlement_formats"],
            original_entitlement_payload_sha256=source["entitlement_payload_sha256"],
            signed_entitlement_payload_sha256=current["entitlement_payload_sha256"],
            entitlement_semantics_preserved=True, XML_and_DER_cross_checked=len(current["entitlement_formats"]) == 2,
            all_directories_ad_hoc=True, nonempty_CMS_absent=True,
        ))
    assert all(sha(path) == digest for path, digest in before.items()), "Input mutated during host verification"
    return dict(
        verified=True, original=str(original), original_sha256=before[str(original)],
        signed=str(signed), signed_sha256=before[str(signed)], slices=rows,
        omitted_original_architectures=[list(key) for key in old if key not in new],
        independent_page_and_special_slot_check=independent,
        original_Apple_signature_revalidated=False, Apple_platform_identity_claimed=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guard-build", help="Guard build.json with images[] input/output hashes")
    parser.add_argument("--signed", action="append", default=[], metavar="NAME=PATH", help="Signed private copy corresponding to a guard image")
    parser.add_argument("--pair", action="append", nargs=2, default=[], metavar=("ORIGINAL", "SIGNED"), help="Verify a pair without a guard build")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    destination = ROOT / args.report
    assert not destination.exists(), "Never overwrite historical evidence"
    items, guard_hash = [], None
    if args.guard_build:
        assert not args.pair
        guard = ROOT / args.guard_build
        guard_hash = sha(guard)
        build = json.loads(guard.read_text())
        choices = {}
        for item in args.signed:
            name, path = item.split("=", 1)
            assert name and name not in choices
            choices[name] = path
        assert len(build["images"]) == 4, "Expected four original compatibility services"
        assert set(choices) == {item["name"] for item in build["images"]}, "Every service needs a signed copy"
        for item in build["images"]:
            assert sha(ROOT / item["input"]) == item["input_sha256"], "Original source SHA changed"
            assert sha(ROOT / item["output"]) == item["patched_sha256"], "Frozen unsigned compatibility input changed"
            items.append((item["name"], ROOT / item["input"], ROOT / choices[item["name"]], item["expected_identifier"]))
    else:
        assert args.pair and not args.signed
        items = [(str(index), ROOT / original, ROOT / signed, None) for index, (original, signed) in enumerate(args.pair)]
    checks = []
    for name, original, signed, identifier in items:
        try:
            check = verify_pair(original, signed, identifier)
        except (AssertionError, ValueError, KeyError, IndexError, struct.error, OSError) as error:
            check = dict(verified=False, original=str(original), signed=str(signed), error_type=type(error).__name__, error=str(error))
        checks.append(dict(name=name, **check))
    if args.guard_build:
        assert sha(ROOT / args.guard_build) == guard_hash
    report = dict(
        verified=all(item["verified"] for item in checks), checks=checks,
        guard_build=args.guard_build, guard_build_sha256=guard_hash,
        host_only=True, native_execution_attempted=False, files_modified=False,
        local_ad_hoc_only=True, Apple_platform_identity_claimed=False,
        original_Apple_CMS_revalidated=False, certificate_or_device_trust_verified=False,
        sources={name: sha(ROOT / name) for name in [*VERIFIERS, str(Path(__file__).relative_to(ROOT))]},
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"verified": report["verified"], "checks": [{key: item[key] for key in ["name", "verified"]} for item in checks]}, indent=2))
    print(destination)
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
