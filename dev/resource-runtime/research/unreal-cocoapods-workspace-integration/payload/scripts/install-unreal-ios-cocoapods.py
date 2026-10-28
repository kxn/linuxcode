#!/usr/bin/env python3
"""Run original Darwin CocoaPods and verify integration into the generated UE workspace.

Only an explicit invocation without --check starts native processes. The global
native-session lock covers the complete install, inspection, and evidence write.
This entrypoint never runs a UE build or claims that an App has been built.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import runpy
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def clone_session_launcher(profile, command, folder, lock_fd):
    """Keep the parent and launcher flock on one inherited open description."""
    original_name = profile['command'][4]
    check(profile['command'].count(original_name) == 1 and command.count(original_name) == 1,
          'Expected exactly one profile launcher in both commands')
    original = (root / original_name).resolve()
    check(original.parent.parent == root / 'runtime' and original.name == 'darling',
          'Expected the verified runtime/<launcher>/darling layout')
    check(folder.parent == root / 'runtime', 'Private launcher must preserve the project root calculation')
    expected = profile.get('native_codesign', {}).get('files', {}).get(original_name)
    source = original.read_bytes()
    check(expected and hashlib.sha256(source).hexdigest() == expected,
          'Profile launcher is not pinned to its verified source digest')
    check(lock_fd >= 3, 'Session lock must use a dedicated inherited descriptor')
    opened = os.fstat(lock_fd)
    session = (root / 'runtime/session.lock').stat()
    check((opened.st_dev, opened.st_ino) == (session.st_dev, session.st_ino),
          'Inherited descriptor is not the global native session lock')
    old = b'exec 9>"$project/runtime/session.lock"\n'
    new = f'exec 9<&{lock_fd}\n'.encode('ascii')
    check(source.count(old) == 1 and source.count(b'\nflock 9\n') == 1,
          'Expected exactly one original lock open and flock operation')
    project_line = b'project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)\n'
    check(source.count(project_line) == 1, 'Unexpected original launcher project-root calculation')
    namespace = original.with_name('runtime-ns.sh')
    namespace_reference = ('"$project/' + str(namespace.relative_to(root)) + '"').encode()
    check(source.count(namespace_reference) == 1, 'Unexpected original namespace entrypoint')
    private = folder / 'darling'
    check(not private.exists(), 'Private launcher already exists')
    private.write_bytes(source.replace(old, new, 1))
    private.chmod(original.stat().st_mode & 0o777)
    selected = list(command)
    selected[selected.index(original_name)] = str(private.relative_to(root))
    return selected, dict(
        original_launcher=original_name, original_launcher_sha256=expected,
        private_launcher=str(private.relative_to(root)), private_launcher_sha256=digest(private),
        preserved_namespace=str(namespace.relative_to(root)), preserved_namespace_sha256=digest(namespace),
        inherited_lock_fd=lock_fd, lock_open_replacement_count=1,
        parent_launcher_command_occurrences=1, original_flock_preserved=True,
        parent_and_child_share_lock_open_description=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-report', required=True, help='prepared.json emitted by prepare-unreal-ios-cocoapods.py')
    parser.add_argument('--stage', default='artifacts/private-procfs-v5-stage.json')
    parser.add_argument('--check', action='store_true', help='Read-only validation; do not run native code')
    args = parser.parse_args()
    report_path = (root / args.project_report).resolve()
    check(report_path.is_relative_to(root), 'Preparation report must be in this workspace')
    prepared = json.loads(report_path.read_text())
    check(prepared.get('fixture_authored_by_linuxcode') and prepared.get('ordinary_UE_project_fixture'),
          'Use the ordinary UE fixture CocoaPods preparation report')
    project = (root / prepared['project']).resolve()
    check(project.is_relative_to(root / 'runtime'), 'Fixture must be inside runtime/')
    check(not (project / 'Pods').exists(), 'Pods already exist; this entrypoint verifies a fresh install')
    input_digests = {}
    for name, expected in prepared['files'].items():
        path = (root / name).resolve()
        check(path.is_relative_to(root) and path.is_file() and digest(path) == expected,
              'Prepared source input changed: ' + name)
        input_digests[path] = expected
    pbx = project / prepared['ue_xcode_project'] / 'project.pbxproj'
    workspace = project / (prepared['target'] + ' (IOS).xcworkspace/contents.xcworkspacedata')
    for path in (pbx, workspace):
        check(digest(path) == prepared['original_inputs'][str(path.relative_to(root))]['sha256'],
              'Generated UE project changed since preparation: ' + str(path))
        input_digests[path] = prepared['original_inputs'][str(path.relative_to(root))]['sha256']
    if args.check:
        print(json.dumps(dict(prepared_inputs_verified=True, project=prepared['project'],
                              target=prepared['target'], runtime_stage=args.stage,
                              native_process_started=False), indent=2))
        return
    with (root / 'runtime/session.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Native session is busy; no native process was started') from None
        check(not (project / 'Pods').exists() and
              all(path.is_file() and digest(path) == expected for path, expected in input_digests.items()),
              'Prepared project changed during preflight; no native process was started')
        folder = Path(tempfile.mkdtemp(prefix='unreal-ios-pod-install-', dir=root / 'runtime'))
        guest = lambda path: '/Volumes/SystemRoot/workspace/' + str(path.relative_to(root))
        inspector = root / 'scripts/inspect-unreal-pods-project.rb'
        script = folder / 'run.sh'
        after = folder / 'verified.json'
        script.write_text('#!/bin/bash\nset -e\nulimit -c 0\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\n' +
                          'cd ' + shlex.quote(guest(project)) + '\n' +
                          'pod install --no-repo-update\n' +
                          shlex.join(['/usr/bin/ruby', guest(inspector), 'verify', guest(project),
                                      prepared['target'], guest(after), guest(project / 'unreal-pods-before.json')]) + '\n')
        module = runpy.run_path(str(root / 'scripts/private-procfs-runtime-profile.py'))
        profile = module['profile'](stage=args.stage)
        # Keep Xcode-specific library overrides outside Ruby's process tree.
        command = [arg for arg in profile['command'][:-2]
                   if not arg.startswith(('DYLD_LIBRARY_PATH=', 'DYLD_FRAMEWORK_PATH='))] + ['/bin/bash', guest(script)]
        command[3] = '300'
        command, launcher = clone_session_launcher(profile, command, folder, lock.fileno())
        env = module['environment'](profile)
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
            env.pop(name, None)
        with (folder / 'run.log').open('w') as stream:
            result = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    pass_fds=(lock.fileno(),))
        error = None
        verified = False
        try:
            metadata = json.loads(after.read_text())
            check(metadata['project_metadata_verified'], 'Post-install inspection failed')
            check((project / 'Podfile.lock').read_bytes() == (project / 'Pods/Manifest.lock').read_bytes(),
                  'CocoaPods lockfiles differ')
            check('LocalMath (0.1.0)' in (project / 'Podfile.lock').read_text(), 'Expected LocalMath dependency missing')
            verified = result.returncode == 0
        except (OSError, ValueError, KeyError, RuntimeError) as exception:
            error = str(exception)
        files = [Path(__file__), inspector, report_path, root / args.stage,
                 root / launcher['original_launcher'], root / launcher['preserved_namespace'],
                 *[project / name for name in ('Podfile', 'Podfile.lock', 'Pods/Manifest.lock',
                                               'Pods/Pods.xcodeproj/project.pbxproj', 'unreal-pods-before.json',
                                               'unreal-pods-integration.json')], pbx, workspace, *folder.iterdir()]
        record = dict(verified=verified, pod_install_verified=verified,
                      project=prepared['project'], target=prepared['target'],
                      project_report=str(report_path.relative_to(root)), runtime_stage=args.stage,
                      command=command, outer_status=result.returncode, metadata_error=error,
                      global_native_session_lock_held=True,
                      session_launcher=launcher,
                      ordinary_UE_project_fixture=True, fixture_authored_by_linuxcode=True,
                      engine_source_modified=False, Ruby_Xcode_framework_overrides=False,
                      pod_compile_verified=False, full_app_build_verified=False,
                      files={str(path.relative_to(root)): digest(path) for path in files if path.is_file()})
        (folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        print((folder / 'run.log').read_text()[-6000:], 'EVIDENCE', folder / 'result.json')
        raise SystemExit(0 if verified else 1)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
