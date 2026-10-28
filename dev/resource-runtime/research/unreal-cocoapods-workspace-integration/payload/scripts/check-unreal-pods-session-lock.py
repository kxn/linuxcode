#!/usr/bin/env python3
"""Check Pod installer launcher lock inheritance using Linux processes only.

Select the real verified profile, then exercise only the cloned launcher's
root/lock prefix in an isolated repository and lock file. Never execute its
namespace, Darling, runtime guard, or any Mach-O binary.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import runpy
import select
import signal
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', default='artifacts/private-procfs-v5-stage.json')
    args = parser.parse_args()
    installer = runpy.run_path(str(root / 'scripts/install-unreal-ios-cocoapods.py'))
    module = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))
    profile = module['profile'](stage=args.stage)
    original = root / profile['command'][4]
    original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
    folder = Path(tempfile.mkdtemp(prefix='unreal-pods-session-lock-check-', dir=root / 'runtime'))
    fixture = folder / 'repository'
    (fixture / original.relative_to(root).parent).mkdir(parents=True)
    copied = fixture / original.relative_to(root)
    shutil.copy2(original, copied)
    shutil.copy2(original.with_name('runtime-ns.sh'), copied.with_name('runtime-ns.sh'))
    # The original prefix only checks -x here. This file is never executed.
    sentinel = fixture / 'runtime/rootfs/usr/bin/darling'
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text('Not an executable program; used only by Bash -x file test.\n')
    sentinel.chmod(0o700)
    session_path = fixture / 'runtime/session.lock'
    clone = installer['clone_session_launcher']
    clone.__globals__['root'] = fixture
    command = list(profile['command'])
    marker = b'if [[ -f "$project/runtime/state/host-cpu-haswell.json" ]]; then\n'
    metadata = []
    # Preserve the real profile's timeout wrapper, using a short test deadline.
    wrapper = list(profile['command'][:4])
    assert wrapper[:3] == ['timeout', '-k', '5']
    wrapper[3] = '3'

    def contender(expected):
        result = subprocess.run([sys.executable, '-c',
                                 'import fcntl,sys; f=open(sys.argv[1],"a"); '
                                 'fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)', str(session_path)],
                                text=True, capture_output=True, timeout=3)
        assert (result.returncode == 0) == expected, result.stderr

    def prepare_prefix(lock, label):
        run_folder = fixture / 'runtime' / label
        run_folder.mkdir()
        selected, record = clone(profile, command, run_folder, lock.fileno())
        metadata.append(record)
        private = fixture / record['private_launcher']
        source = copied.read_bytes()
        expected = source.replace(b'exec 9>"$project/runtime/session.lock"\n',
                                  f'exec 9<&{lock.fileno()}\n'.encode(), 1)
        assert private.read_bytes() == expected
        assert selected.count(record['private_launcher']) == 1 and profile['command'][4] not in selected
        assert expected.count(marker) == 1
        prefix = expected.partition(marker)[0]
        assert prefix.endswith(b'flock 9\n')
        probe = run_folder / 'lock-prefix-only.sh'
        probe.write_bytes(prefix + b'printf "LOCK_PREFIX_ACQUIRED\\n"\nread -r finish\n')
        return probe

    def start_prefix(probe, lock):
        child = subprocess.Popen(wrapper + ['/bin/bash', str(probe)], cwd=fixture,
                                 pass_fds=(lock.fileno(),), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 start_new_session=True)
        try:
            readable, _, _ = select.select([child.stdout], [], [], 3)
            assert readable, 'Inherited launcher prefix deadlocked'
            assert child.stdout.readline() == 'LOCK_PREFIX_ACQUIRED\n'
        except BaseException:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=3)
            raise
        return child

    # Child exit must not release the parent's exclusive lock.
    with session_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe = prepare_prefix(lock, 'child-exits-first')
        no_fd = subprocess.run(wrapper + ['/bin/bash', str(probe)], cwd=fixture,
                               input='finish\n', text=True, capture_output=True, timeout=3)
        assert no_fd.returncode != 0 and 'Bad file descriptor' in no_fd.stderr
        child = start_prefix(probe, lock)
        contender(False)
        stdout, stderr = child.communicate('finish\n', timeout=3)
        assert child.returncode == 0, stderr
        contender(False)
    contender(True)

    # Parent exit/close must not release the inherited child's exclusive lock.
    lock = session_path.open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe = prepare_prefix(lock, 'parent-closes-first')
        child = start_prefix(probe, lock)
    finally:
        lock.close()
    try:
        contender(False)
    finally:
        stdout, stderr = child.communicate('finish\n', timeout=3)
    assert child.returncode == 0, stderr
    contender(True)

    # Unexpected launcher multiplicity must fail before a clone is written.
    with session_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        refusal = fixture / 'runtime/refuse-duplicate-command'
        refusal.mkdir()
        try:
            clone(profile, command + [profile['command'][4]], refusal, lock.fileno())
            raise AssertionError('Duplicate launcher was accepted')
        except RuntimeError as error:
            assert 'exactly one profile launcher' in str(error)
        assert not (refusal / 'darling').exists()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_sha
    record = dict(
        verified=True, scope='Linux Bash launcher lock prefix only, isolated session lock',
        runtime_stage=args.stage, original_launcher=str(original.relative_to(root)),
        original_launcher_sha256=original_sha, original_launcher_unchanged=True,
        exact_single_line_clone_verified=True, inherited_flock_reentry_did_not_block=True,
        profile_timeout_wrapper_preserved_in_lock_probes=True,
        independent_processes_excluded_while_parent_or_child_holds_lock=True,
        child_exit_preserves_parent_lock=True, parent_close_preserves_child_lock=True,
        lock_released_after_last_close=True, omitted_pass_fds_rejected=True,
        duplicate_launcher_command_rejected=True, launchers=metadata,
        native_process_started=False, namespace_entered=False,
        pod_install_verified=False, full_app_build_verified=False,
        files={str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in (Path(__file__).resolve(), root / 'scripts/install-unreal-ios-cocoapods.py')})
    (folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print('EVIDENCE', folder / 'result.json')


if __name__ == '__main__':
    main()
