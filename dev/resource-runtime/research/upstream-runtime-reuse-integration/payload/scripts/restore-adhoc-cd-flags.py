#!/usr/bin/env python3
"""Restore original CodeDirectory options in new local ad-hoc service copies.

Inputs must already pass independent ad-hoc/page/entitlement verification, with
no CMS payload. Each directory maps to the same original architecture and slot.
Only its flags word becomes original_flags | CS_ADHOC; executable bytes and all
immutable inputs are preserved. This neither signs nor claims Apple identity.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import shutil
import struct
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SIGNATURE_HELPER = ROOT / "scripts/verify-service-compat-signatures.py"
MACHO_HELPER = ROOT / "scripts/build-pinned-platform-guards.py"
signatures = runpy.run_path(str(SIGNATURE_HELPER))
macho = runpy.run_path(str(MACHO_HELPER))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signed-build", required=True)
    args = parser.parse_args()
    manifest = ROOT / args.signed_build
    manifest_hash = sha(manifest)
    build = json.loads(manifest.read_text())
    guard = ROOT / build["guard_build"]
    assert sha(guard) == build["guard_build_sha256"]
    guard_build = json.loads(guard.read_text())
    expected = {item["name"]: item for item in guard_build["images"]}
    assert len(expected) == 4 and {item["name"] for item in build["images"]} == set(expected)
    prepared = []
    for image in build["images"]:
        context = expected[image["name"]]
        original, source = ROOT / image["original"], ROOT / image["output"]
        assert image["original"] == context["input"] and sha(original) == context["input_sha256"] == image["original_sha256"]
        assert image["unsigned_compatibility"] == context["output"]
        assert sha(ROOT / context["output"]) == context["patched_sha256"] == image["unsigned_compatibility_sha256"]
        source_hash = sha(source)
        assert source_hash == image["output_sha256"]
        signatures["verify_pair"](original, source, context["expected_identifier"])
        old = signatures["metadata"](original)
        current = signatures["metadata"](source)
        changed = bytearray(source.read_bytes())
        changes, audits = [], []
        for arch in macho["slices"](bytes(changed)):
            key = (arch["cpu_type"], arch["cpu_subtype"])
            previous, signed = old[key], current[key]
            assert not signed["cms_payload_present"]
            source_directories = {item["slot"]: item for item in previous["directories"]}
            new_directories = {item["slot"]: item for item in signed["directories"]}
            assert set(source_directories) == set(new_directories)
            sig = macho["signature_metadata"](arch["data"])
            absolute = arch["slice_offset"] + sig["signature_offset"]
            count = struct.unpack_from(">I", changed, absolute + 8)[0]
            for index in range(count):
                slot, offset = struct.unpack_from(">II", changed, absolute + 12 + 8 * index)
                if slot not in new_directories:
                    continue
                prior = source_directories[slot]["flags"]
                present = new_directories[slot]["flags"]
                assert prior in (0, 0x2000), "This pinned cohort has unexpected original flags"
                assert present & 2 and not prior & 2
                desired = prior | 2
                flags_at = absolute + offset + 12
                assert struct.unpack_from(">I", changed, flags_at)[0] == present
                audits.append(dict(cpu_type=key[0], cpu_subtype=key[1], slot=slot,
                                   original_flags=prior, initial_ad_hoc_flags=present, restored_ad_hoc_flags=desired))
                if desired != present:
                    before = bytes(changed[flags_at:flags_at + 4])
                    struct.pack_into(">I", changed, flags_at, desired)
                    changes.append(dict(cpu_type=key[0], cpu_subtype=key[1], slot=slot,
                                        file_offset=flags_at, bytes_replaced=4,
                                        before=before.hex(), after=bytes(changed[flags_at:flags_at + 4]).hex()))
        check = bytearray(source.read_bytes())
        for change in changes:
            at = change["file_offset"]
            check[at:at + 4] = bytes.fromhex(change["after"])
        assert check == changed and sha(source) == source_hash
        prepared.append((image, source, bytes(changed), audits, changes))
    # All context checks precede creating new candidates.
    folder = Path(tempfile.mkdtemp(prefix="zsign-security-platform-guards-flags-v2-", dir=ROOT / "runtime"))
    rows = []
    for image, source, data, audits, changes in prepared:
        subdir = folder / image["name"]
        subdir.mkdir()
        target = subdir / image["name"]
        target.write_bytes(data)
        shutil.copymode(source, target)
        independent = signatures["verify_pair"](ROOT / image["original"], target, expected[image["name"]]["expected_identifier"])
        current = signatures["metadata"](target)
        for audit in audits:
            arch = current[(audit["cpu_type"], audit["cpu_subtype"])]
            assert next(item for item in arch["directories"] if item["slot"] == audit["slot"])["flags"] == audit["restored_ad_hoc_flags"]
        rows.append(dict(**{k: v for k, v in image.items() if k not in ("output", "output_sha256")},
                         zsign_output=str(source.relative_to(ROOT)), zsign_output_sha256=sha(source),
                         output=str(target.relative_to(ROOT)), output_sha256=sha(target),
                         CodeDirectory_flag_audit=audits, CodeDirectory_flag_restoration=changes,
                         independent_signature_check=independent))
    assert sha(manifest) == manifest_hash and sha(guard) == build["guard_build_sha256"]
    report = dict(**{k: v for k, v in build.items() if k not in ("images", "elapsed_seconds", "installed", "Apple_platform_identity_claimed")},
                  images=rows, parent_signed_build=args.signed_build, parent_signed_build_sha256=manifest_hash,
                  additional_step="Restore original per-architecture/per-slot CodeDirectory flags | CS_ADHOC on verified CMS-free ad-hoc copies",
                  original_CodeDirectory_flags_preserved=True, CodeDirectory_header_restoration_only=True,
                  executable_bytes_modified=False, source_sha256=sha(Path(__file__)),
                  reused_helpers_sha256={str(path.relative_to(ROOT)): sha(path) for path in [SIGNATURE_HELPER, MACHO_HELPER]},
                  native_execution_attempted=False, installed=False, Apple_platform_identity_claimed=False)
    destination = folder / "build.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
