#!/usr/bin/env python3
"""Fetch only official Mac Intel Editor/iOS PKGs into a new private input folder.

Uses the same resumable ranged-download and official MD5 validation strategy as
fetch-unity-linux-editor.py. Does not install, launch, or access licensing data.
"""
from pathlib import Path
import argparse, base64, concurrent.futures, hashlib, json, shutil, time, urllib.request

VERSION = '6000.3.27f1'
REVISION = '672d562a42a7'
API = 'https://services.api.unity.com/unity/editor/release/v1/releases?version=' + VERSION
EXPECTED = {
    'editor': (5245239594, 'md5-4H2gEFfv8E9FNQC2Bj1GOw==', 'MacEditorInstaller/Unity-6000.3.27f1.pkg'),
    'ios': (471089015, 'md5-Uf9ZLV1GH52DqoQIzaY1jg==', 'MacEditorTargetInstaller/UnitySetup-iOS-Support-for-Editor-6000.3.27f1.pkg'),
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New folder, or this downloader\'s resumable folder')
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    folder = args.output.resolve()
    if folder.exists():
        previous = json.loads((folder / 'inputs.json').read_text()) if (folder / 'inputs.json').is_file() else {}
        if (previous.get('version'), previous.get('revision'), previous.get('platform'), previous.get('architecture')) != (VERSION, REVISION, 'MAC_OS', 'X86_64'):
            raise SystemExit('Existing output is not this exact Mac Intel input folder')
    with urllib.request.urlopen(API, timeout=30) as response:
        metadata = json.load(response)
    release, = metadata['results']
    assert release['version'] == VERSION
    editor, = [d for d in release['downloads'] if d['platform'] == 'MAC_OS' and d['architecture'] == 'X86_64']
    ios, = [m for m in editor['modules'] if m['id'] == 'ios']
    items = dict(editor=editor, ios=ios)
    for name, item in items.items():
        size, integrity, suffix = EXPECTED[name]
        assert item['downloadSize']['value'] == size and item['integrity'] == integrity
        assert item['url'] == 'https://download.unity3d.com/download_unity/' + REVISION + '/' + suffix
        assert item['type'] == 'PKG'
    # Leave 50 GiB for concurrent engine work in addition to new archive bytes.
    free = shutil.disk_usage(folder.parent).free
    required = sum(x[0] for x in EXPECTED.values()) + 50 * 1024 ** 3
    if free < required:
        raise SystemExit('Insufficient space: requires archives plus 50 GiB reserve')
    folder.mkdir(parents=True, exist_ok=True)
    record = dict(version=VERSION, revision=REVISION, platform='MAC_OS', architecture='X86_64',
                  metadata_url=API, free_bytes_before=free, editor=editor, ios=ios)
    (folder / 'inputs.json').write_text(json.dumps(record, indent=2) + '\n')
    (folder / 'official-release.json').write_text(json.dumps(metadata, indent=2) + '\n')
    chunk = 16 * 1024 * 1024
    def fetch(job):
        name, item, start, end, path = job
        count = end - start + 1
        if path.exists() and path.stat().st_size == count:
            return
        pending = path.with_suffix('.pending')
        for attempt in range(5):
            try:
                existing = pending.stat().st_size if pending.exists() else 0
                if existing > count:
                    raise RuntimeError('Partial range exceeds expected size')
                if existing == count:
                    pending.replace(path)
                    return
                request = urllib.request.Request(item['url'], headers={'Range': f'bytes={start + existing}-{end}'})
                with urllib.request.urlopen(request, timeout=45) as response, pending.open('ab') as out:
                    assert response.status == 206
                    assert response.headers['Content-Range'] == f'bytes {start + existing}-{end}/{item["downloadSize"]["value"]}'
                    copied = existing
                    while data := response.read(min(1024 * 1024, count - copied + 1)):
                        copied += len(data)
                        if copied > count:
                            raise RuntimeError('Range overrun')
                        out.write(data)
                    assert copied == count
                pending.replace(path)
                return
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(attempt + 1)
    jobs = []
    for name, item in items.items():
        parts = folder / (name + '-parts')
        parts.mkdir(exist_ok=True)
        size = item['downloadSize']['value']
        jobs += [(name, item, start, min(size, start + chunk) - 1, parts / (str(start) + '.part')) for start in range(0, size, chunk)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for index, _ in enumerate(pool.map(fetch, jobs), 1):
            if index % 16 == 0:
                print(f'Validated ranges {index}/{len(jobs)}', flush=True)
    verified = {}
    for name, item in items.items():
        output = folder / (name + '.pkg')
        pending = folder / (name + '.assembled')
        md5, sha = hashlib.md5(), hashlib.sha256()
        with pending.open('wb') as out:
            for job in jobs:
                if job[0] != name:
                    continue
                with job[4].open('rb') as source:
                    while data := source.read(4 * 1024 * 1024):
                        out.write(data); md5.update(data); sha.update(data)
        assert md5.digest() == base64.b64decode(item['integrity'].split('-', 1)[1])
        assert pending.stat().st_size == item['downloadSize']['value']
        pending.replace(output)
        verified[name] = dict(path=str(output), bytes=output.stat().st_size, sha256=sha.hexdigest(), official_integrity=item['integrity'], url=item['url'])
    result = dict(verified=True, version=VERSION, revision=REVISION, platform='MAC_OS', architecture='X86_64', files=verified,
                  installed=False, editor_launched=False, macos_license_verified=False, ios_export_verified=False)
    (folder / 'verified-downloads.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
