#!/usr/bin/env python3
"""Verify re-signing preserved complete execution contents of guarded inputs.

This deliberately checks the concrete candidates strictly: identical FAT shape,
Mach headers, load commands and every byte outside LC_CODE_SIGNATURE's payload.
Legitimate future LINKEDIT/signature layout changes fail for explicit review.
No code is executed and no signature policy or trust decision is changed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import struct

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts/build-pinned-platform-guards.py"
helpers = runpy.run_path(str(HELPER))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def section_rows(binary):
    flags = {}
    for kind, at, size in helpers["commands"](binary):
        if kind != 0x19:
            continue
        count = struct.unpack_from("<I", binary, at + 64)[0]
        assert 72 + 80 * count <= size
        for index in range(count):
            pos = at + 72 + index * 80
            name = binary[pos:pos + 16].split(b"\0")[0].decode()
            segment = binary[pos + 16:pos + 32].split(b"\0")[0].decode()
            key = (segment, name)
            assert key not in flags
            flags[key] = struct.unpack_from("<I", binary, pos + 64)[0]
    result = []
    for segment, name, address, size, offset in helpers["sections"](binary):
        attributes = flags[(segment, name)]
        zero_fill = attributes & 255 in (1, 12, 18)
        if not zero_fill:
            assert offset <= len(binary) and size <= len(binary) - offset
        result.append(dict(segment=segment, section=name, address=address, size=size,
                           file_offset=offset, flags=attributes, zero_fill=zero_fill,
                           bytes_sha256=None if zero_fill else sha(binary[offset:offset + size])))
    return result


def verify_image(row):
    original = ROOT / row["unsigned_compatibility"]
    signed = ROOT / row["output"]
    a, b = original.read_bytes(), signed.read_bytes()
    assert sha(a) == row["unsigned_compatibility_sha256"]
    assert sha(b) == row["output_sha256"]
    old, new = list(helpers["slices"](a)), list(helpers["slices"](b))
    assert [(x["cpu_type"], x["cpu_subtype"]) for x in old] == [(x["cpu_type"], x["cpu_subtype"]) for x in new]
    # For these concrete zsign outputs no layout adjustment occurred. Comparing
    # every header/command byte is stronger than masking permitted size fields.
    assert len(a) == len(b)
    first = min(x["slice_offset"] for x in old)
    assert first == min(x["slice_offset"] for x in new) and a[:first] == b[:first]
    results = []
    cursor = first
    for before, after in zip(old, new):
        assert before["slice_offset"] == after["slice_offset"] and before["slice_size"] == after["slice_size"]
        base = before["slice_offset"]
        assert a[cursor:base] == b[cursor:base], "FAT inter-slice padding changed"
        x, y = before["data"], after["data"]
        assert x[:32] == y[:32], "Mach header changed"
        commands = list(helpers["commands"](x))
        assert commands == list(helpers["commands"](y))
        assert all(x[at:at + size] == y[at:at + size] for _, at, size in commands), "Load command changed"
        old_sections, new_sections = section_rows(x), section_rows(y)
        assert old_sections == new_sections, "Section metadata or execution content changed"
        old_meta, new_meta = helpers["signature_metadata"](x), helpers["signature_metadata"](y)
        start, capacity = old_meta["signature_offset"], old_meta["signature_capacity"]
        assert start == new_meta["signature_offset"] and capacity == new_meta["signature_capacity"]
        assert x[:start] == y[:start] and x[start + capacity:] == y[start + capacity:], "Bytes outside signature payload changed"
        results.append(dict(cpu_type=before["cpu_type"], cpu_subtype=before["cpu_subtype"],
                            slice_offset=base, slice_size=before["slice_size"],
                            Mach_header_identical=True, all_load_commands_identical=True,
                            load_command_count=len(commands), CodeSignature_and_LINKEDIT_layout_unchanged=True,
                            sections=old_sections, all_section_metadata_and_bytes_preserved=True,
                            signature_offset=start, signature_capacity=capacity,
                            bytes_before_signature_sha256=sha(x[:start]),
                            bytes_after_signature_sha256=sha(x[start + capacity:]),
                            every_non_signature_byte_preserved=True))
        cursor = base + before["slice_size"]
    assert a[cursor:] == b[cursor:], "FAT trailing padding changed"
    assert sha(original.read_bytes()) == row["unsigned_compatibility_sha256"] and sha(signed.read_bytes()) == row["output_sha256"]
    return dict(name=row["name"], verified=True, unsigned_compatibility=row["unsigned_compatibility"],
                unsigned_compatibility_sha256=sha(a), signed=row["output"], signed_sha256=sha(b),
                FAT_header_and_padding_identical=True, slices=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signed-build", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    manifest = ROOT / args.signed_build
    before = sha(manifest.read_bytes())
    build = json.loads(manifest.read_text())
    assert len(build["images"]) == 4
    checks = []
    for row in build["images"]:
        try:
            checks.append(verify_image(row))
        except (AssertionError, ValueError, KeyError, OSError, struct.error) as error:
            checks.append(dict(name=row["name"], verified=False, error_type=type(error).__name__, error=str(error)))
    assert sha(manifest.read_bytes()) == before
    report = dict(verified=all(row["verified"] for row in checks), checks=checks,
                  signed_build=args.signed_build, signed_build_sha256=before,
                  comparison_scope="unsigned audited compatibility guard -> local signed copy",
                  header_or_load_command_fields_ignored=[], complete_non_signature_bytes_checked=True,
                  native_execution_attempted=False, inputs_modified=False,
                  signature_hash_verification_separate=True, Apple_platform_identity_claimed=False,
                  source_sha256=sha(Path(__file__).read_bytes()), reused_helpers=str(HELPER.relative_to(ROOT)),
                  reused_helpers_sha256=sha(HELPER.read_bytes()))
    destination = ROOT / args.report
    assert not destination.exists()
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"verified": report["verified"], "checks": [{k: row[k] for k in ["name", "verified"]} for row in checks]}, indent=2))
    print(destination)
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
