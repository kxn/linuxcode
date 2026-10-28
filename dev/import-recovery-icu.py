#!/usr/bin/env python3
"""Import only pinned Recovery ICU inputs with host Linux 7zip into a new private directory."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import plistlib
import subprocess
import sys

HERE = Path(__file__).resolve().parent
LOCK = HERE / 'locks/recovery-icu-25G83.lock.json'
RECEIPT = 'recovery-icu-import.json'


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_lock():
    lock = json.loads(LOCK.read_text())
    check(lock['schema'] == 1, 'Unsupported Recovery ICU input lock')
    for name in (lock['archive_root'], *lock['files']):
        path = Path(name)
        check(name and not path.is_absolute() and '..' not in path.parts, 'Unsafe locked archive path')
    return lock


def image_input(image, lock):
    image = Path(image).expanduser().resolve(strict=True)
    check(image.is_file() and image.stat().st_size == lock['image']['length'], 'Recovery image length mismatch; extraction was not started')
    digest = sha(image)
    check(digest == lock['image']['sha256'], 'Recovery image SHA256 mismatch; extraction was not started')
    return image, dict(path=str(image), length=image.stat().st_size, sha256=digest)


def inspect_files(directory, lock, exact=False):
    directory = Path(directory).resolve(strict=True)
    rows = {}
    for name, pin in lock['files'].items():
        relative = Path(lock['archive_root']) / name
        path = directory / relative
        cursor = directory
        for part in relative.parts:
            cursor = cursor / part
            check(not cursor.is_symlink(), 'Refusing imported resource symlink: ' + str(relative))
        check(path.is_file() and path.stat().st_size == pin['length'], 'Imported resource length mismatch: ' + name)
        digest = sha(path)
        check(digest == pin['sha256'], 'Imported resource SHA256 mismatch: ' + name)
        rows[name] = dict(path=relative.as_posix(), length=path.stat().st_size, sha256=digest)
    version = plistlib.loads((directory / lock['archive_root'] / 'System/Library/CoreServices/SystemVersion.plist').read_bytes())
    check(version.get('ProductVersion') == lock['version'] and version.get('ProductBuildVersion') == lock['build'],
          'Imported Recovery version/build mismatch')
    if exact:
        expected = {row['path'] for row in rows.values()}
        for path in directory.rglob('*'):
            check(not path.is_symlink(), 'Unexpected extracted symlink')
            if path.is_file():
                check(path.relative_to(directory).as_posix() in expected | {RECEIPT, 'extract-7zip.log'},
                      'Unexpected file outside selected Recovery ICU inputs: ' + str(path.relative_to(directory)))
    return dict(files=rows, version=version['ProductVersion'], build=version['ProductBuildVersion'])


def extraction_command(tool, image, directory, lock):
    return [str(tool), 'x', '-y', '-mmt=1', '-o' + str(directory), str(image),
            *[str(Path(lock['archive_root']) / name) for name in lock['files']]]


def import_inputs(image, directory, tool, lock):
    directory = Path(directory).expanduser()
    check(not directory.exists() and not directory.is_symlink(), 'Output directory must be new; no existing runtime or input tree is overwritten')
    directory = directory.resolve()
    check(not directory.is_relative_to(HERE.parent), 'Output must be private and outside the distribution checkout')
    image, selected = image_input(image, lock)
    tool = Path(tool).expanduser().resolve(strict=True)
    with tool.open('rb') as stream:
        check(stream.read(4) == b'\x7fELF', 'Use the actual Linux 7zip executable, such as /usr/lib/7zip/7z')
    check(os.access(tool, os.X_OK), 'Linux 7zip executable is not executable')
    command = extraction_command(tool, image, directory, lock)
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(verified=False, scope=lock['scope'], image=selected, command=command,
                   sevenzip=str(tool), sevenzip_sha256=sha(tool), input_lock_sha256=sha(LOCK),
                   output=str(directory), source_identity='Pinned Recovery 26.6.2 / 25G83',
                   signed_chunklist_verified_this_run=False,
                   image_matches_previously_signed_chunklist_verified_pin=True,
                   native_runtime_launched=False, session_lock_acquired=False,
                   frozen_candidate_modified=False, default_runtime_changed=False,
                   private_identity_or_activation_files_accessed=False,
                   full_recovery_input_set_imported=False, cold_Darling_Xcode_rebuild_ready=False)
    try:
        with (directory / 'extract-7zip.log').open('w') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        receipt['sevenzip_exit_status'] = result.returncode
        check(result.returncode == 0, '7zip extraction failed; private diagnostic output was preserved')
        receipt.update(inspect_files(directory, lock, exact=True), verified=True)
    except (OSError, ValueError) as error:
        receipt['error'] = str(error)
        raise
    finally:
        receipt['extract_log_sha256'] = sha(directory / 'extract-7zip.log') if (directory / 'extract-7zip.log').is_file() else None
        (directory / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, help='Explicit local BaseSystem.dmg matching the pinned SHA256')
    parser.add_argument('--output', type=Path, required=True, help='New private output, or existing imported output for --inspect')
    parser.add_argument('--sevenzip', type=Path, help='Actual Linux ELF 7zip executable; no Darling or Apple extractor')
    parser.add_argument('--plan', action='store_true', help='Print exact selection without reading/extracting an image')
    parser.add_argument('--inspect', action='store_true', help='Read-only verification of an existing import and receipt')
    args = parser.parse_args()
    check(platform.system() == 'Linux', 'This input preparation entrypoint supports host Linux')
    lock = load_lock()
    if args.inspect:
        receipt = json.loads((args.output / RECEIPT).read_text())
        check(receipt.get('verified') and receipt['input_lock_sha256'] == sha(LOCK), 'Import receipt is not verified against this input lock')
        check(receipt['image']['sha256'] == lock['image']['sha256'], 'Import receipt references another Recovery image')
        result = dict(verified=True, import_rechecked=True, **inspect_files(args.output, lock),
                      signed_chunklist_verified_this_run=False, native_runtime_launched=False,
                      cold_Darling_Xcode_rebuild_ready=False)
    else:
        check(args.image and args.sevenzip, 'Specify --image and --sevenzip for explicit host-only extraction')
        if args.plan:
            result = dict(command=extraction_command(args.sevenzip, args.image, args.output, lock),
                          image_pin=lock['image'], selected_files=lock['files'], commands_executed=False,
                          cold_Darling_Xcode_rebuild_ready=False)
        else:
            result = import_inputs(args.image, args.output, args.sevenzip, lock)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('Recovery ICU import: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from None
