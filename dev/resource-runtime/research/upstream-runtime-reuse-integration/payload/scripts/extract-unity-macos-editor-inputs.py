#!/usr/bin/env python3
"""Host-only extraction of verified Unity PKGs; never executes installer or Editor."""
from pathlib import Path
import argparse, base64, gzip, hashlib, json, os, plistlib, runpy, shutil, subprocess

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Must not already exist')
    parser.add_argument('--sevenzip', required=True, type=Path, help='Existing Linux ELF 7zip')
    args = parser.parse_args()
    source = args.inputs.resolve(strict=True)
    output = args.output.absolute()
    tool = args.sevenzip.resolve(strict=True)
    assert tool.open('rb').read(4) == b'\x7fELF', 'Only a host Linux extractor is accepted'
    assert not output.exists() and not output.is_symlink(), 'Output must be new'
    receipt = json.loads((source / 'verified-downloads.json').read_text())
    assert receipt['verified'] and receipt['platform'] == 'MAC_OS' and receipt['architecture'] == 'X86_64'
    assert receipt['version'] == '6000.3.27f1' and receipt['revision'] == '672d562a42a7'
    # Keep enough room for payload intermediates plus installed trees and engine jobs.
    assert shutil.disk_usage(output.parent).free > 70 * 1024 ** 3
    pins = runpy.run_path(str(Path(__file__).resolve().with_name('fetch-unity-macos-editor-inputs.py')))['EXPECTED']
    assert set(receipt['files']) == set(pins)
    for name, row in receipt['files'].items():
        path = Path(row['path']).resolve(strict=True)
        size, integrity, suffix = pins[name]
        assert path.parent == source and path.stat().st_size == row['bytes'] == size
        assert row['official_integrity'] == integrity
        assert row['url'] == 'https://download.unity3d.com/download_unity/672d562a42a7/' + suffix
        md5, actual_sha = hashlib.md5(), hashlib.sha256()
        with path.open('rb') as stream:
            while data := stream.read(4 * 1024 * 1024):
                md5.update(data); actual_sha.update(data)
        assert actual_sha.hexdigest() == row['sha256'], 'Input differs from verified download'
        assert md5.digest() == base64.b64decode(integrity.split('-', 1)[1]), 'Official MD5 mismatch'
    output.mkdir()
    work = output / 'archive-components'; work.mkdir()
    commands = []
    for name, entry in [('editor', 'Unity.pkg.tmp/Payload'), ('ios', 'TargetSupport.pkg.tmp/Payload')]:
        part = work / name; part.mkdir()
        cmd = [str(tool), 'x', '-y', '-mmt=1', '-o' + str(part), receipt['files'][name]['path'], entry]
        commands.append(cmd)
        with (part / '7zip.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        payload = part / entry
        # GNU cpio lists/checks original archive names before extracting them.
        with gzip.open(payload, 'rb') as stream:
            check = subprocess.Popen(['cpio', '-it', '--quiet'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            import threading
            def feed():
                try:
                    shutil.copyfileobj(stream, check.stdin, 4 * 1024 * 1024)
                finally:
                    check.stdin.close()
            writer = threading.Thread(target=feed); writer.start()
            names = check.stdout.read(); errors = check.stderr.read(); status = check.wait(); writer.join()
            assert status == 0, errors.decode(errors='replace')
        for raw in names.splitlines():
            path = Path(os.fsdecode(raw))
            assert not path.is_absolute() and '..' not in path.parts, 'Unsafe archive member'
        destination = output if name == 'editor' else output / 'Unity/PlaybackEngines'
        destination.mkdir(parents=True, exist_ok=True)
        # No chown, registration, installer scripts, prefix writes, or licensing steps.
        cmd = ['cpio', '--extract', '--make-directories', '--no-absolute-filenames', '--no-preserve-owner', '--quiet']
        commands.append(cmd)
        with gzip.open(payload, 'rb') as stream, (part / 'cpio.log').open('w') as log:
            child = subprocess.Popen(cmd, cwd=destination, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
            try:
                shutil.copyfileobj(stream, child.stdin, 4 * 1024 * 1024)
            finally:
                child.stdin.close()
            assert child.wait() == 0, 'See private cpio.log'
        payload.unlink()
    app = output / 'Unity/Unity.app'
    editor = app / 'Contents/MacOS/Unity'
    support = output / 'Unity/PlaybackEngines/iOSSupport'
    assert editor.is_file() and support.is_dir(), 'Unexpected official payload layout'
    plist = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    assert plist['CFBundleVersion'] == receipt['version']
    magic = editor.open('rb').read(4)
    assert magic in (bytes.fromhex('cffaedfe'), bytes.fromhex('cafebabe'), bytes.fromhex('bebafeca')), 'Editor is not Mach-O'
    record = dict(host_payload_extraction_verified=True, installed_into_system_prefix=False,
                  installer_scripts_executed=False, version=receipt['version'], revision=receipt['revision'],
                  editor=str(editor), editor_sha256=sha(editor), ios_support=str(support),
                  bundle_version=plist['CFBundleVersion'], inputs_receipt=str(source / 'verified-downloads.json'),
                  inputs_receipt_sha256=sha(source / 'verified-downloads.json'),
                  input_files=receipt['files'],
                  extractor=str(tool), extractor_sha256=sha(tool), commands=commands,
                  editor_launched=False, macos_license_verified=False, ios_export_verified=False)
    (output / 'extraction.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))

if __name__ == '__main__':
    main()
