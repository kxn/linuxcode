#!/usr/bin/env python3
"""Apply reviewed resource-development sources to the fixed runtime snapshot.

No downloads, compilation, Darling execution, Git reset, index update or runtime
installation is performed. All target files are preflighted before any change.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / 'overlay.json').read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('Unsafe overlay path: ' + name)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Refusing symlink in overlay path: ' + str(cursor))
    if not cursor.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('Overlay path escapes its root: ' + name)
    return cursor


def identity(path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError('Expected a regular source file: ' + str(path))
    return {'sha256': sha(path), 'mode': stat.S_IMODE(path.stat().st_mode)}


def matches(observed, expected):
    # Git tracks content and executability, not the caller's umask/group bits.
    if observed is None or expected is None:
        return observed is expected
    return (observed['sha256'] == expected['sha256']
            and bool(observed['mode'] & 0o111) == bool(expected['mode'] & 0o111))


def overlay_identity(item):
    return {'sha256': item['sha256'], 'mode': item['mode']}


def baseline_identity(item):
    return None if item['baseline_sha256'] is None else {
        'sha256': item['baseline_sha256'], 'mode': item['baseline_mode']}


def preflight(workspace):
    head = subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip()
    if head != MANIFEST['base']['commit']:
        raise ValueError('Workspace HEAD must be the fixed ' + MANIFEST['base']['tag'] + ' commit; no checkout/reset attempted')
    protected = list(MANIFEST['files']) + list(MANIFEST['baseline_dependencies']) + [
        'checkpoint/' + name for name in MANIFEST['base']['checkpoint']]
    staged = subprocess.check_output(['git', '-C', str(workspace), 'diff', '--cached',
        '--name-only', '-z', 'HEAD', '--', *protected])
    if staged:
        raise ValueError('Staged developer changes preserved; refusing overlay over: '
                         + staged.decode().replace('\0', ', ').rstrip(', '))
    for name, expected in MANIFEST['base']['checkpoint'].items():
        path = safe_path(workspace, 'checkpoint/' + name)
        if not path.is_file() or sha(path) != expected:
            raise ValueError('Fixed snapshot checkpoint changed: ' + name)
    for name, expected in MANIFEST['baseline_dependencies'].items():
        path = safe_path(workspace, name)
        if not path.is_file() or sha(path) != expected:
            raise ValueError('Required snapshot dependency changed or missing: ' + name)
    changes, already = [], []
    for name, item in MANIFEST['files'].items():
        payload = safe_path(HERE / 'payload', name)
        if not matches(identity(payload), overlay_identity(item)):
            raise ValueError('Overlay payload checksum/mode changed: ' + name)
        destination = safe_path(workspace, name)
        observed = identity(destination)
        if matches(observed, overlay_identity(item)):
            already.append(name)
        elif matches(observed, baseline_identity(item)):
            after = overlay_identity(item)
            if observed:
                after['mode'] = (observed['mode'] & ~0o111) | (after['mode'] & 0o111)
            changes.append({'path': name, 'before': observed, 'after': after})
        else:
            raise ValueError('Developer changes preserved; refusing different target: ' + name)
    return changes, already


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def private_directory(workspace):
    directory = safe_path(workspace, '.linuxcode-overlays')
    if directory.exists() and not directory.is_dir():
        raise ValueError('Overlay backup path is not a directory')
    directory.mkdir(exist_ok=True)
    return directory


def restore_one(workspace, backup, entry):
    destination = safe_path(workspace, entry['path'])
    if entry['before'] is None:
        destination.unlink()
    else:
        original = safe_path(backup / 'original', entry['path'])
        if identity(original) != entry['before']:
            raise ValueError('Backup content or mode changed: ' + entry['path'])
        fd, pending = tempfile.mkstemp(prefix='.linuxcode-restore-', dir=destination.parent)
        os.close(fd)
        try:
            shutil.copyfile(original, pending)
            os.chmod(pending, entry['before']['mode'])
            os.replace(pending, destination)
        finally:
            if os.path.exists(pending):
                os.unlink(pending)


def apply(workspace, plan=False):
    changes, already = preflight(workspace)
    result = {'overlay': MANIFEST['name'], 'workspace': str(workspace),
              'files_to_change': [x['path'] for x in changes], 'already_equal': already,
              'plan': plan, 'runtime_execution': False}
    if plan or not changes:
        result['changed'] = False
        return result
    directory = private_directory(workspace)
    descriptor = os.open(directory / 'resource-runtime.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        changes, already = preflight(workspace)
        if not changes:
            return {**result, 'files_to_change': [], 'already_equal': already, 'changed': False}
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex
        backup = directory / name
        (backup / 'original').mkdir(parents=True)
        (backup / 'pending').mkdir()
        record = {'schema': 1, 'workspace': str(workspace), 'overlay': MANIFEST['name'],
                  'overlay_manifest_sha256': sha(HERE / 'overlay.json'),
                  'base_commit': MANIFEST['base']['commit'], 'state': 'preparing', 'files': changes}
        write_json(backup / 'receipt.json', record)
        # Prepare every backup and replacement before touching any destination.
        for entry in changes:
            destination = safe_path(workspace, entry['path'])
            if entry['before'] is not None:
                original = safe_path(backup / 'original', entry['path'])
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(destination, original)
                os.chmod(original, entry['before']['mode'])
                if identity(original) != entry['before']:
                    raise ValueError('Source changed while creating backup: ' + entry['path'])
            pending = safe_path(backup / 'pending', entry['path'])
            pending.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(HERE / 'payload', entry['path']), pending)
            os.chmod(pending, entry['after']['mode'])
        record['state'] = 'prepared'
        write_json(backup / 'receipt.json', record)
        replaced = []
        try:
            for entry in changes:
                destination = safe_path(workspace, entry['path'])
                if identity(destination) != entry['before']:
                    raise ValueError('Source changed after preflight: ' + entry['path'])
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(safe_path(backup / 'pending', entry['path']), destination)
                replaced.append(entry)
            record['state'] = 'applied'
            write_json(backup / 'receipt.json', record)
        except BaseException:
            errors = []
            for entry in reversed(replaced):
                try:
                    if identity(safe_path(workspace, entry['path'])) != entry['after']:
                        raise ValueError('Concurrent developer change after replacement: ' + entry['path'])
                    restore_one(workspace, backup, entry)
                except (OSError, ValueError) as error:
                    errors.append(str(error))
            record.update(state='rollback_failed' if errors else 'rolled_back', rollback_errors=errors)
            write_json(backup / 'receipt.json', record)
            if errors:
                raise RuntimeError('Rollback needs review; preserved backups at ' + str(backup) + ': ' + '; '.join(errors))
            raise
    return {**result, 'changed': True, 'backup': str(backup),
            'rollback_command': [sys.executable, str(HERE / 'apply-overlay.py'), '--workspace', str(workspace), '--rollback', str(backup)]}


def rollback(workspace, backup, plan=False):
    expected_parent = workspace / '.linuxcode-overlays'
    backup = backup.resolve()
    if backup.parent != expected_parent or backup.is_symlink():
        raise ValueError('Backup must be directly inside this workspace/.linuxcode-overlays')
    receipt = safe_path(backup, 'receipt.json')
    record = json.loads(receipt.read_text())
    if record['workspace'] != str(workspace) or record['state'] != 'applied':
        raise ValueError('Backup does not describe an applied overlay in this workspace')
    # Preflight every restored/deleted path before making any rollback change.
    for entry in record['files']:
        if identity(safe_path(workspace, entry['path'])) != entry['after']:
            raise ValueError('Refusing rollback over later developer edits: ' + entry['path'])
        if entry['before'] is not None and identity(safe_path(backup / 'original', entry['path'])) != entry['before']:
            raise ValueError('Backup changed: ' + entry['path'])
    if not plan:
        descriptor = os.open(expected_parent / 'resource-runtime.lock', os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Repeat complete validation under the same lock before restoring.
            for entry in record['files']:
                if identity(safe_path(workspace, entry['path'])) != entry['after']:
                    raise ValueError('Source changed during rollback preflight: ' + entry['path'])
            for entry in reversed(record['files']):
                restore_one(workspace, backup, entry)
            record['state'] = 'rolled_back'
            write_json(receipt, record)
    return {'workspace': str(workspace), 'backup': str(backup), 'rolled_back': not plan,
            'plan': plan, 'paths': [x['path'] for x in record['files']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--rollback', type=Path, help='Restore a reviewed backup; refuses subsequent developer changes')
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve(strict=True)
    result = rollback(workspace, args.rollback, args.plan) if args.rollback else apply(workspace, args.plan)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('resource-runtime overlay: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
