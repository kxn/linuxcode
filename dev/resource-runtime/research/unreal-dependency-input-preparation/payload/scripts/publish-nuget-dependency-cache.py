#!/usr/bin/env python3
"""Publish complete host-restored dependency inputs without replacing existing packages."""
from pathlib import Path
import argparse, base64, hashlib, json, os, re, subprocess, tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prefetch', required=True)
parser.add_argument('--packages-target', required=True)
parser.add_argument('--http-cache-target', required=True)
parser.add_argument('--http-cache-source', help='Existing HTTP metadata cache when a fully seeded restore made no network requests')
args = parser.parse_args()
source = (root / args.prefetch).resolve(strict=True)
packages = (root / args.packages_target).resolve()
http = (root / args.http_cache_target).resolve()
assert all(p.is_relative_to(root / 'runtime') for p in [source, packages, http])
restored = json.loads((source / 'restore-result.json').read_text())
assert restored['status'] == 0 and restored['dependency_restore_only'] and restored['packages_ready']
assert not http.exists(), 'HTTP cache destination must be fresh'
http_source = ((root / args.http_cache_source).resolve(strict=True) if args.http_cache_source
               else source / 'home/.local/share/NuGet/http-cache')
assert http_source.is_dir() and http_source.is_relative_to(root / 'runtime'), 'Provide an existing cache if a seeded restore created none'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
content_hashes = {}
for manifest in (source / 'source').rglob('project.assets.json'):
    assets = json.loads(manifest.read_text())
    for identity, library in assets['libraries'].items():
        if library.get('type') != 'package': continue
        identity = identity.lower(); value = library['sha512']
        assert len(base64.b64decode(value, validate=True)) == 64
        assert identity not in content_hashes or content_hashes[identity] == value
        content_hashes[identity] = value
rows = []
for archive in sorted((source / 'packages').glob('*/*/*.nupkg')):
    directory = archive.parent; version = directory.name; package = directory.parent.name
    assert all(re.fullmatch(r'[a-z0-9_.+\-]+', value) for value in [package, version])
    checksum = next(directory.glob('*.nupkg.sha512'))
    actual = base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    assert actual == checksum.read_text().strip(), archive
    metadata = directory / '.nupkg.metadata'
    # Signed packages have a canonical content hash distinct from the raw ZIP
    # hash. Preserve NuGet's metadata and compare it with its restore manifest.
    content_hash = json.loads(metadata.read_text())['contentHash']
    assert len(base64.b64decode(content_hash, validate=True)) == 64
    expected_content_hash = content_hashes.get(package + '/' + version)
    if expected_content_hash is not None: assert content_hash == expected_content_hash
    rows.append(dict(package=package, version=version, archive=archive.name,
                     sha512_base64=actual, restored_content_hash=content_hash,
                     matched_final_restore_manifest=expected_content_hash is not None))
assert rows
staging = Path(tempfile.mkdtemp(prefix='nuget-cache-import-', dir=root / 'runtime'))
subprocess.run(['cp', '-a', '--reflink=auto', str(source / 'packages'), str(staging / 'packages')], check=True)
packages.mkdir(parents=True, exist_ok=True)
for row in rows:
    destination = packages / row['package'] / row['version']
    pending = staging / 'packages' / row['package'] / row['version']
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        original = destination / row['archive']
        assert original.is_file() and base64.b64encode(hashlib.sha512(original.read_bytes()).digest()).decode() == row['sha512_base64']
        row['published'] = False
    else:
        os.rename(pending, destination); row['published'] = True
subprocess.run(['cp', '-a', '--reflink=auto', str(http_source), str(http)], check=True)
record = dict(verified=True, prefetch=args.prefetch, restore_result_sha256=sha(source / 'restore-result.json'),
              packages_target=args.packages_target, http_cache_target=args.http_cache_target,
              packages=rows, package_count=len(rows), existing_packages_never_replaced=True,
              HTTP_cache_source=str(http_source.relative_to(root)),
              HTTP_cache_files={str(p.relative_to(http)): sha(p) for p in http.rglob('*') if p.is_file()},
              inputs_only=True, original_macOS_UBT_build_proof=False, driver_sha256=sha(Path(__file__)))
(staging / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('PUBLISHED', len(rows), 'dependency package versions', staging.relative_to(root) / 'result.json')
