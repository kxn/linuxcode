#!/usr/bin/env python3
"""Fetch selected official dependency inputs from the user's local UE manifest."""
from pathlib import Path, PurePosixPath
import argparse, concurrent.futures, fnmatch, gzip, hashlib, json, os, tempfile
import urllib.request
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', default='vendor/unreal-engine')
parser.add_argument('--file', action='append', required=True, help='Manifest path or glob; quote globs')
args = parser.parse_args()
source = (root / args.source).resolve(strict=True)
manifest = source / 'Engine/Build/Commit.gitdeps.xml'
document = ET.parse(manifest).getroot()
files = [x.attrib for x in document.find('Files')]
selected = []
for pattern in args.file:
    matches = [f for f in files if fnmatch.fnmatchcase(f['Name'], pattern)]
    assert matches, pattern
    selected.extend(matches)
selected = list({f['Name']: f for f in selected}.values())
for f in selected:
    path = PurePosixPath(f['Name'])
    assert not path.is_absolute() and '..' not in path.parts
    assert (source / f['Name']).resolve().is_relative_to(source)
blobs = {x.attrib['Hash']: x.attrib for x in document.find('Blobs')}
packs = {x.attrib['Hash']: x.attrib for x in document.find('Packs')}
folder = Path(tempfile.mkdtemp(prefix='unreal-dependency-inputs-', dir=root / 'runtime'))
folder.chmod(0o700)
groups = {}
for f in selected:
    destination = source / f['Name']
    if destination.exists():
        assert hashlib.sha1(destination.read_bytes()).hexdigest() == f['Hash'], f['Name']
        continue
    blob = blobs[f['Hash']]
    groups.setdefault(blob['PackHash'], []).append((f, blob))

def download(item):
    pack_hash, entries = item
    pack = packs[pack_hash]
    url = document.attrib['BaseUrl'].rstrip('/') + '/' + pack['RemotePath'] + '/' + pack_hash
    assert url.startswith('https://cdn.unrealengine.com/dependencies/')
    with urllib.request.urlopen(url, timeout=120) as response:
        compressed = response.read()
    assert len(compressed) == int(pack['CompressedSize'])
    data = gzip.decompress(compressed)
    assert len(data) == int(pack['Size']) and hashlib.sha1(data).hexdigest() == pack_hash
    rows = []
    for f, blob in entries:
        start = int(blob['PackOffset']); size = int(blob['Size'])
        piece = data[start:start + size]
        assert len(piece) == size and hashlib.sha1(piece).hexdigest() == f['Hash']
        destination = source / f['Name']; destination.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite a user-modified input, even if it appeared during download.
        try:
            with destination.open('xb') as stream: stream.write(piece)
        except FileExistsError:
            assert hashlib.sha1(destination.read_bytes()).hexdigest() == f['Hash']
        if f.get('IsExecutable') == 'true': destination.chmod(destination.stat().st_mode | 0o111)
        rows.append(dict(path=f['Name'], manifest_SHA1=f['Hash'], size=size, pack_SHA1=pack_hash))
    print('FETCHED', len(rows), 'input(s)', flush=True)
    return rows

print('FETCHING', len(groups), 'packs for', len(selected), 'selected inputs', flush=True)
rows = []
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for result in pool.map(download, groups.items()): rows.extend(result)
record = dict(verified=True, official_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
              selected_count=len(selected), downloaded_count=len(rows), files=rows,
              existing_inputs_never_replaced=True, original_project_files_modified=False,
              licensed_inputs_not_for_publication=True,
              driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
print('EVIDENCE', folder.relative_to(root) / 'result.json')
