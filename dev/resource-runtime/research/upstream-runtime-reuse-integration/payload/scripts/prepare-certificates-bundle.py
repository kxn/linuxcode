#!/usr/bin/env python3
"""Copy and verify an entire version-matched OS Certificates.bundle, host only.

The resulting runtime-provider.json is one entry for the existing generic
service-cohort runtime_providers list. No installed image or trust data changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def inventory(directory):
    rows = {}
    for path in [directory, *sorted(directory.rglob('*'))]:
        name = '.' if path == directory else path.relative_to(directory).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        assert not mode & 0o7000, path
        if path.is_symlink():
            target = os.readlink(path)
            assert not PurePosixPath(target).is_absolute(), path
            assert path.resolve(strict=True).is_relative_to(directory), path
            rows[name] = dict(type='symlink', target=target, mode=mode)
        elif path.is_dir():
            rows[name] = dict(type='directory', mode=mode)
        else:
            assert path.is_file(), path
            rows[name] = dict(type='file', mode=mode, size=path.stat().st_size, sha256=sha(path))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--source-system-version', required=True)
    parser.add_argument('--expected-os-build', required=True)
    parser.add_argument('--output-dir', required=True, help='New directory under runtime/')
    args = parser.parse_args()
    bundle = (ROOT / args.bundle).resolve(strict=True)
    system_version = (ROOT / args.source_system_version).resolve(strict=True)
    output = (ROOT / args.output_dir).resolve()
    assert bundle.is_relative_to(ROOT / 'runtime') and bundle.is_dir()
    assert system_version.is_relative_to(ROOT / 'runtime') and system_version.is_file()
    assert output.is_relative_to(ROOT / 'runtime') and not output.exists()
    os_root = system_version.parents[3]
    assert system_version.relative_to(os_root) == Path('System/Library/CoreServices/SystemVersion.plist')
    assert bundle.relative_to(os_root) == Path('System/Library/Security/Certificates.bundle')
    os_info = plistlib.loads(system_version.read_bytes())
    assert os_info['ProductBuildVersion'] == args.expected_os_build
    before = inventory(bundle)
    resources = bundle / 'Contents/Resources'
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    version = plistlib.loads((bundle / 'Contents/version.plist').read_bytes())
    asset = plistlib.loads((resources / 'AssetVersion.plist').read_bytes())
    manifest = plistlib.loads((resources / 'manifest.data').read_bytes())
    assert info['CFBundleIdentifier'] == 'com.apple.Certificates'
    assert info['CFBundleVersion'] == version['CFBundleVersion']
    assert int(info['CFBundleVersion']) == asset['VersionNumber'] == manifest['VersionNumber']
    assert isinstance(manifest, dict)
    verified = []
    for name, digest in manifest.items():
        if name == 'VersionNumber':
            continue
        spelling = PurePosixPath(name)
        assert name == spelling.as_posix() and not spelling.is_absolute()
        assert all(part not in ('', '.', '..') for part in name.split('/'))
        path = (resources / name).resolve(strict=True)
        assert path.is_relative_to(resources) and path.is_file()
        assert isinstance(digest, bytes) and len(digest) == 32
        assert hashlib.sha256(path.read_bytes()).digest() == digest, name
        verified.append(name)
    assert {'AssetVersion.plist', 'EVRoots.plist', 'certsIndex.data', 'certsTable.data'} <= set(verified)
    anchors = plistlib.loads((resources / 'Anchors.plist').read_bytes())
    assert isinstance(anchors, dict) and anchors
    records = []
    for key, values in anchors.items():
        assert isinstance(key, str) and isinstance(values, list) and values
        for record in values:
            assert isinstance(record, dict)
            assert isinstance(record['type'], str) and isinstance(record['oids'], list)
            assert all(isinstance(oid, str) for oid in record['oids'])
            for field in ['sha2', 'spki-sha2']:
                digest = record[field]
                assert isinstance(digest, str) and len(digest) == 64 and len(bytes.fromhex(digest)) == 32
            records.append(record)
    references = {record['sha2'].upper() for record in records}
    certificates = list((resources / 'Anchors').iterdir())
    assert all(path.is_file() and not path.is_symlink() and path.suffix == '.cer' for path in certificates)
    assert references == {path.stem for path in certificates}
    assert all(sha(path).upper() == path.stem for path in certificates)

    output.mkdir(parents=True, mode=0o755)
    candidate = output / 'Certificates.bundle'
    shutil.copytree(bundle, candidate, symlinks=True, copy_function=shutil.copy2)
    assert before == inventory(candidate) == inventory(bundle)
    files = {}
    for name, row in before.items():
        if row['type'] == 'file':
            files[name] = dict(sha256=row['sha256'])
        elif row['type'] == 'symlink':
            files[name] = dict(symlink=row['target'])
    provider = dict(destination='System/Library/Security/Certificates.bundle', source=relative(candidate), files=files)
    provider_path = output / 'runtime-provider.json'
    provider_path.write_text(json.dumps(provider, indent=2) + '\n')
    script = Path(__file__).resolve()
    report = dict(
        host_verified=True, installed=False, native_execution=False,
        source=relative(bundle), candidate=relative(candidate),
        source_system_version=relative(system_version), source_system_version_sha256=sha(system_version),
        source_os_build=args.expected_os_build, bundle_version=info['CFBundleVersion'], asset_version=asset,
        source_inventory=before, source_unchanged=True, complete_bundle_copy_identical=True,
        resource_files=sum(row['type'] == 'file' for row in before.values()),
        resource_bytes=sum(row.get('size', 0) for row in before.values()),
        manifest_SHA256_members_verified=verified,
        anchors=dict(keys=len(anchors), records=len(records), certificate_files=len(certificates),
                     missing_certificates=0, unreferenced_certificates=0, certificate_filenames_equal_SHA256=True),
        zero_length_original_entries=[name for name, row in before.items() if row['type'] == 'file' and row['size'] == 0],
        bundle_signature_verified=False,
        signature_caveat='The original extracted signature files are preserved; this tool does not verify Apple bundle signatures.',
        runtime_provider=relative(provider_path), runtime_provider_sha256=sha(provider_path),
        installation_contract='Merge the provider entry into the existing common service cohort; install the whole bundle in both root and prefix before the first Mach-O. No per-program environment.',
        trust_contents_modified=False, sealed_image_modified=False,
        tool=relative(script), tool_sha256=sha(script))
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(relative(output / 'build.json'))


if __name__ == '__main__':
    main()
