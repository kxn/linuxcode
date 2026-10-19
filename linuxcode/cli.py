"""Linuxcode setup and verified milestone launcher; Python standard library only."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import runpy
import shlex
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
import urllib.request

SOURCE = Path(__file__).resolve().parent.parent
LOCK = json.loads((SOURCE / 'config/dependencies.lock.json').read_text())
GUEST = '/Volumes/SystemRoot/workspace/'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def fail(message):
    raise RuntimeError(message)


def run(argv, **kwargs):
    print('+ ' + shlex.join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), check=True, **kwargs)


def git(workspace, *args):
    return subprocess.check_output(['git', '-C', str(workspace), *args], text=True).strip()


def verify_workspace(workspace):
    expected = LOCK['workspace']
    if git(workspace, 'rev-parse', 'HEAD') != expected['commit']:
        fail('Workspace HEAD differs from the locked milestone; no reset was attempted.')
    manifest = workspace / 'checkpoint/workspace-files.json'
    if sha(manifest) != expected['manifest_sha256']:
        fail('Workspace manifest checksum differs from the locked milestone.')
    files = json.loads(manifest.read_text())
    for relative, digest in files.items():
        path = workspace / relative
        if not path.is_file() or sha(path) != digest:
            fail(f'Locked workspace file changed: {relative}')
    return len(files)


def fetch(workspace):
    if not workspace.exists() or not any(workspace.iterdir()):
        workspace.mkdir(parents=True, exist_ok=True)
        run(['git', 'init', workspace])
        run(['git', '-C', workspace, 'remote', 'add', 'origin', LOCK['workspace']['url']])
        run(['git', '-C', workspace, 'fetch', '--depth=1', 'origin', LOCK['workspace']['commit']])
        run(['git', '-C', workspace, 'checkout', '--detach', 'FETCH_HEAD'])
    count = verify_workspace(workspace)
    print(f'Locked milestone workspace verified: {count} files, {workspace}')


def doctor(workspace, args):
    commands = ['git', 'bash', 'unshare', 'mount', 'chroot', 'flock', 'cp', 'cpio',
                'curl', 'unzip', 'tar', 'clang-19', 'ld64.lld-19', 'sudo']
    missing = [name for name in commands if not shutil.which(name)]
    probe = subprocess.run(['unshare', '--user', '--map-root-user', 'true'],
                           capture_output=True, text=True) if shutil.which('unshare') else None
    cpu = Path('/proc/cpuinfo').read_text() if Path('/proc/cpuinfo').exists() else ''
    flags = set(next((line.split(':', 1)[1].split() for line in cpu.splitlines()
                      if line.startswith('flags')), []))
    ancestor = workspace
    while not ancestor.exists():
        ancestor = ancestor.parent
    result = {'host': platform.platform(), 'architecture': platform.machine(),
              'python': platform.python_version(), 'missing_commands': missing,
              'user_namespace_available': probe is not None and probe.returncode == 0,
              'user_namespace_error': probe.stderr.strip() if probe and probe.returncode else None,
              'haswell_cpu_flags': all(flag in flags for flag in ['avx', 'avx2', 'bmi1', 'bmi2', 'fma']),
              'free_gib': round(shutil.disk_usage(ancestor).free / 2**30, 1),
              'workspace': str(workspace), 'full_candidate_cold_install_ready': False,
              'baseline_ready': platform.system() == 'Linux' and platform.machine() == 'x86_64'
                                and not missing and probe is not None and probe.returncode == 0}
    print(json.dumps(result, indent=2))
    if args.report:
        save(args.report, result)
    if not result['baseline_ready']:
        return 2
    return 0


def cache_assets(workspace):
    directory = workspace / 'downloads'
    directory.mkdir(parents=True, exist_ok=True)
    for asset in LOCK['baseline_assets']:
        destination = directory / asset['name']
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + '.part')
            print('Downloading ' + asset['url'], flush=True)
            with urllib.request.urlopen(asset['url'], timeout=60) as source, temporary.open('wb') as output:
                shutil.copyfileobj(source, output, 8 * 1024 * 1024)
            if sha(temporary) != asset['sha256']:
                fail(f'Download checksum mismatch: {temporary}')
            temporary.replace(destination)
        if sha(destination) != asset['sha256']:
            fail(f'Cached asset checksum mismatch: {destination}')
        print('Verified ' + str(destination))


def intel_xcode(app):
    binary = app / 'Contents/Developer/usr/bin/xcodebuild'
    data = binary.read_bytes()
    magic = data[:4]
    if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe'):
        arches = [struct.unpack_from('<I', data, 4)[0]]
    elif magic in (b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'):
        arches = [struct.unpack_from('>I', data, 4)[0]]
    elif magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'):
        endian = '>' if magic[0] == 0xca else '<'
        count = struct.unpack_from(endian + 'I', data, 4)[0]
        stride = 32 if magic in (b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca') else 20
        if not 1 <= count <= 64 or 8 + count * stride > len(data):
            fail('Invalid Mach-O architecture table.')
        arches = [struct.unpack_from(endian + 'I', data, 8 + i * stride)[0] for i in range(count)]
    else:
        fail('xcodebuild is not recognized as Mach-O.')
    if 0x01000007 not in arches:
        fail('This Xcode has no Intel x86_64 executable.')
    if sha(binary) != LOCK['xcode']['xcodebuild_sha256']:
        fail('Xcode binary differs from the tested version; unsupported input was not installed.')
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    version = plistlib.loads((app / 'Contents/version.plist').read_bytes())
    return {'version': info.get('CFBundleShortVersionString'),
            'build': version.get('ProductBuildVersion'), 'architectures': arches,
            'xcodebuild_sha256': sha(binary)}


def install_xcode(workspace, xip, expected_sha=None):
    verify_workspace(workspace)
    xip = xip.resolve(strict=True)
    xip_sha = sha(xip)
    expected_sha = expected_sha or LOCK['xcode'].get('xip_sha256')
    if expected_sha and xip_sha != expected_sha:
        fail('XIP SHA256 mismatch; extraction was not started.')
    prefix = workspace / 'runtime/state/prefix'
    destination = prefix / 'Applications/Xcode.app'
    extraction = workspace / 'runtime/xcode-extract'
    state = workspace / 'artifacts/distribution-xcode-install.json'
    if destination.exists():
        if not state.exists():
            fail('Existing Xcode has no installer receipt; refusing to overwrite.')
        receipt = json.loads(state.read_text())
        if receipt['xip_sha256'] != xip_sha or intel_xcode(destination) != receipt['xcode']:
            fail('Existing Xcode differs from this input or its installation receipt.')
        print('Xcode installation already matches input and receipt.')
        return receipt
    if extraction.exists() and any(extraction.iterdir()):
        fail(f'Incomplete or foreign extraction exists: {extraction}; keep it for diagnosis and use a fresh workspace.')
    (workspace / 'runtime').mkdir(exist_ok=True)
    (workspace / 'logs').mkdir(exist_ok=True)
    (workspace / 'artifacts').mkdir(exist_ok=True)
    with (workspace / 'runtime/session.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run([sys.executable, workspace / 'scripts/extract-xip.py', xip, extraction,
             '--report', workspace / 'artifacts/distribution-xip-extraction.json',
             '--log', workspace / 'logs/distribution-xip-cpio.log'])
        app = extraction / 'Xcode.app'
        details = intel_xcode(app)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name('Xcode.app.importing')
        if staging.exists():
            fail('Unfinished Xcode import exists; it was not overwritten.')
        run(['cp', '-a', '--reflink=auto', app, staging])
        staging.rename(destination)
        receipt = {'xip': str(xip), 'xip_sha256': xip_sha,
                   'xip_expected_sha256_verified': bool(expected_sha),
                   'xar_content_checksum_verified': True, 'xip_cms_signature_verified': False,
                   'xcode': details, 'destination': str(destination),
                   'workspace_commit': LOCK['workspace']['commit'],
                   'xcode_select_pending': True, 'full_xcodebuild_environment_ready': False}
        save(state, receipt)
    print('Xcode imported into isolated prefix; selection will be completed by setup.')
    return receipt


def initialize_prefix(workspace):
    prefix = workspace / 'runtime/state/prefix'
    account = prefix / 'private/etc/passwd'
    holding = workspace / 'runtime/offline-xcode-prefix'
    if account.exists():
        if holding.exists():
            fail('An offline Xcode initialization holding directory exists; inspect it before continuing.')
        return
    if holding.exists():
        fail('Interrupted offline prefix initialization preserved at ' + str(holding) + '; inspect it before retrying.')
    if prefix.exists():
        receipt = workspace / 'artifacts/distribution-xcode-install.json'
        apps = prefix / 'Applications'
        if (not receipt.exists() or set(p.name for p in prefix.iterdir()) != {'Applications'}
                or not apps.is_dir() or set(p.name for p in apps.iterdir()) != {'Xcode.app'}):
            fail('Uninitialized prefix contains unrecognized data; refusing to move or overwrite it.')
        intel_xcode(apps / 'Xcode.app')
        prefix.rename(holding)
    # Darling creates account files only if the prefix directory does not exist.
    # Keep an offline import outside that path until initialization completes.
    run([workspace / 'bin/darling', 'shell', 'uname', '-a'], cwd=workspace)
    if not account.exists():
        fail('Darling did not initialize its account database; offline input is preserved.')
    if holding.exists():
        destination = prefix / 'Applications/Xcode.app'
        if destination.exists():
            fail('Initialized prefix unexpectedly contains Xcode; offline input is preserved.')
        destination.parent.mkdir(exist_ok=True)
        (holding / 'Applications/Xcode.app').rename(destination)
        (holding / 'Applications').rmdir()
        holding.rmdir()


def setup(workspace, args):
    fetch(workspace)
    host_result = doctor(workspace, argparse.Namespace(report=None))
    if host_result:
        fail('Host dependencies are incomplete; see doctor output and docs/install.md.')
    cache_assets(workspace)
    if not (workspace / 'runtime/.installed').exists():
        run(['bash', workspace / 'scripts/bootstrap.sh'], cwd=workspace)
    initialize_prefix(workspace)
    receipt = install_xcode(workspace, args.xip, args.sha256)
    run([workspace / 'bin/darling', 'shell', '/usr/bin/xcode-select', '--switch',
         '/Applications/Xcode.app/Contents/Developer'], cwd=workspace)
    receipt['xcode_select_pending'] = False
    save(workspace / 'artifacts/distribution-xcode-install.json', receipt)
    print('Base Darling + Xcode installation completed. The milestone candidate is not cold-built by setup.')
    print('Next: python3 linuxcode.py --workspace ' + shlex.quote(str(workspace)) + ' recipe')


def candidate(workspace):
    module = runpy.run_path(str(workspace / LOCK['candidate']['profile']))
    profile = module['profile'](diagnostic=True)
    report_path = workspace / LOCK['candidate']['report']
    record = json.loads(report_path.read_text())
    if record['exit_status'] != 0 or not record['xcode_process_returned']:
        fail('Candidate evidence does not record successful native return.')
    if sha(workspace / record['log']) != record['log_sha256']:
        fail('Candidate success log checksum changed.')
    text = (workspace / record['log']).read_text()
    if 'BUILD SUCCEEDED' not in text or not re.search(r'^SERVICE_RUNTIME_XCODE_STATUS 0$', text, re.M):
        fail('Candidate log does not contain the successful native build status.')
    if record['source_runtime'] != profile['source_runtime']:
        fail('Candidate evidence and runtime profile do not select identical source components.')
    if sha(workspace / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild') != LOCK['xcode']['xcodebuild_sha256']:
        fail('Installed original xcodebuild differs from the locked milestone.')
    for job in record['jobs']:
        if sha(workspace / job['path']) != job['sha256']:
            fail('Recorded service job changed: ' + job['path'])
    return module, profile, record


def adopt(workspace, state):
    _, profile, record = candidate(workspace)
    state.mkdir(parents=True, exist_ok=True)
    save(state / 'adopted.json', {'workspace': str(workspace),
         'source_runtime': profile['source_runtime'],
         'evidence_report_sha256': sha(workspace / LOCK['candidate']['report']),
         'diagnostic_policy': True, 'signed_builds_ready': False})
    binary = state / 'bin/xcodebuild'
    binary.parent.mkdir(exist_ok=True)
    binary.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, str(SOURCE / 'linuxcode.py'),
                      '--state', str(state), 'xcodebuild', '--']) + ' "$@"\n')
    binary.chmod(0o755)
    print('Adopted verified milestone candidate. Add to this shell or CI PATH:')
    print('export PATH=' + shlex.quote(str(binary.parent)) + ':"$PATH"')
    print('The candidate still uses the recorded permissive CoreServices diagnostic policy.')


def guest_path(path, workspace):
    path = Path(path).resolve()
    try:
        return GUEST + str(path.relative_to(workspace))
    except ValueError:
        # runtime-ns exposes only its workspace inside the Linux rootfs.
        fail(f'Path is outside the mounted workspace: {path}. Place the project under {workspace}.')


PATH_OPTIONS = {'-project', '-workspace', '-derivedDataPath', '-archivePath', '-exportPath',
                '-exportOptionsPlist', '-resultBundlePath', '-clonedSourcePackagesDirPath',
                '-packageCachePath', '-xcconfig', '-testProductsPath', '-testPlan',
                '-testLanguage', '-testRegion'} - {'-testPlan', '-testLanguage', '-testRegion'}


def build_timeout():
    try:
        seconds = int(os.environ.get('LINUXCODE_BUILD_TIMEOUT_SECONDS', '600'))
    except ValueError:
        fail('LINUXCODE_BUILD_TIMEOUT_SECONDS must be an integer from 1 to 86400.')
    if not 1 <= seconds <= 86400:
        fail('LINUXCODE_BUILD_TIMEOUT_SECONDS must be an integer from 1 to 86400.')
    return seconds


def prepare_invocation(workspace, state, argv, dry_run=False):
    adopted = json.loads((state / 'adopted.json').read_text())
    module, profile, record = candidate(workspace)
    if profile['source_runtime'] != adopted['source_runtime']:
        fail('Adopted runtime changed; inspect and adopt again.')
    if sha(workspace / LOCK['candidate']['report']) != adopted['evidence_report_sha256']:
        fail('Adopted success evidence changed; inspect and adopt again.')
    timeout_seconds = build_timeout()
    cwd = guest_path(Path.cwd(), workspace)
    mapped = list(argv)
    for i, value in enumerate(mapped):
        if i and mapped[i - 1] in PATH_OPTIONS:
            if not value.startswith(('/Applications/', '/Volumes/SystemRoot/')):
                mapped[i] = guest_path(value, workspace)
    plan = {'workspace': str(workspace), 'cwd': cwd, 'original_argv': argv, 'mapped_argv': mapped,
            'original_xcodebuild_sha256': LOCK['xcode']['xcodebuild_sha256'],
            'services': [job['job']['Label'] for job in record['jobs']],
            'diagnostic_policy': True, 'signing_ready': False, 'timeout_seconds': timeout_seconds}
    if dry_run:
        return plan, None, None
    invocation = workspace / 'runtime/linuxcode-cli' / (time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
    invocation.mkdir(parents=True)
    jobs = []
    for index, existing in enumerate(record['jobs']):
        job = dict(existing['job'])
        job['EnvironmentVariables'] = dict(job['EnvironmentVariables'])
        job['StandardOutPath'] = job['StandardErrorPath'] = GUEST + str((invocation / f'service-{index}.log').relative_to(workspace))
        path = invocation / f'service-{index}.plist'
        path.write_bytes(plistlib.dumps(job))
        path.chmod(0o644)
        session = '-S Background ' if existing['name'] in ['distnoted-agent', 'cfprefsd-agent'] else ''
        jobs.append((job['Label'], GUEST + str(path.relative_to(workspace)), session))
    script = invocation / 'run.sh'
    script.write_text('#!/bin/bash\nset -e\nloaded=()\n' +
        'cleanup() { local i; for ((i=${#loaded[@]}-1; i>=0; i--)); do launchctl remove "${loaded[$i]}" >/dev/null 2>&1 || true; done; }\ntrap cleanup EXIT\n' +
        'launchctl remove com.apple.FileCoordination >/dev/null 2>&1 || true\n' +
        '\n'.join('launchctl load ' + session + shlex.quote(path) + '\nloaded+=(' + shlex.quote(label) + ')' for label, path, session in jobs) + '\n' +
        '\n'.join('launchctl list ' + shlex.quote(label) for label, _, _ in jobs) + '\n' +
        "printf 'LINUXCODE_SERVICES_LOADED\\n'\n" +
        GUEST + 'artifacts/uniform-type-identifiers-native\n' +
        "printf 'LINUXCODE_UTI_PREFLIGHT_OK\\n'\n" +
        'cd ' + shlex.quote(cwd) + '\nset +e\n' +
        '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild "$@"\n' +
        'status=$?\nprintf "LINUXCODE_NATIVE_XCODE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = profile['command'][:-2] + ['/bin/bash', GUEST + str(script.relative_to(workspace)), *mapped]
    # Preserve the verified launcher environment, with an explicit long build budget.
    command[3] = str(timeout_seconds)
    save(invocation / 'plan.json', plan)
    return plan, invocation, (command, module['environment'](profile))


def checked_exit_status(native, outer):
    if native is None:
        return outer or 125
    return native or outer


def xcodebuild(state, argv, dry_run):
    if argv and argv[0] == '--':
        argv = argv[1:]
    if not argv:
        argv = ['-help']
    adopted = json.loads((state / 'adopted.json').read_text())
    workspace = Path(adopted['workspace'])
    # Serialize service configuration and launch, not only the low-level Darling session.
    with (state / 'launch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        plan, invocation, execution = prepare_invocation(workspace, state, argv, dry_run)
        if dry_run:
            print(json.dumps(plan, indent=2))
            return 0
        command, environment = execution
        output = invocation / 'output.log'
        with output.open('w') as log:
            process = subprocess.Popen(command, cwd=workspace, env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
            outer = process.wait()
        text = output.read_text()
        markers = re.findall(r'^LINUXCODE_NATIVE_XCODE_STATUS ([0-9]+)$', text, re.M)
        native = int(markers[-1]) if markers else None
        # Require both the actual native status and complete outer process cleanup.
        exit_status = checked_exit_status(native, outer)
        save(invocation / 'result.json', {'native_exit_status': native, 'outer_exit_status': outer,
             'exit_status': exit_status, 'full_ci_ready': False, 'log_sha256': sha(output)})
        print('Linuxcode invocation evidence: ' + str(invocation), file=sys.stderr)
        return exit_status


def package(output):
    allowed = ['linuxcode.py', 'linuxcode/cli.py', 'linuxcode/__init__.py',
               'config/dependencies.lock.json', 'config/runtime-recipe.json',
               'README.md', 'docs/install.md', 'docs/runtime-inputs.md', 'LICENSE', '.gitignore',
               'validation/2026-10-19.json',
               'tests/test_installer.py', 'dev/linuxcode-dev', 'dev/README.md',
               'dev/debian-packages.txt', 'dev/locks/developer.lock.json',
               'dev/locks/source-manifest.json']
    resource = 'dev/resource-runtime/'
    overlay = json.loads((SOURCE / resource / 'overlay.json').read_text())
    allowed += [resource + name for name in ('README.md', 'apply-overlay.py',
        'build-resources.py', 'overlay.json', 'evidence/summary.json', 'tests/test_overlay.py')]
    for relative, entry in overlay['files'].items():
        name = Path(relative)
        if name.is_absolute() or '..' in name.parts or name.suffix not in ('.py', '.json', '.swift', '.c'):
            fail('Invalid developer source payload path: ' + relative)
        payload = resource + 'payload/' + relative
        if sha(SOURCE / payload) != entry['sha256']:
            fail('Developer source payload checksum mismatch: ' + relative)
        allowed.append(payload)
    output = output.resolve()
    if output.exists():
        fail('Refusing to replace an existing public source package.')
    output.parent.mkdir(parents=True, exist_ok=True)
    for relative in allowed:
        path = SOURCE / relative
        if not path.is_file() or path.is_symlink():
            fail('Public package allowlist input is not a regular file: ' + relative)
    temporary = output.with_name(output.name + '.part')
    if temporary.exists():
        fail('Unfinished source package exists: ' + str(temporary))
    with tarfile.open(temporary, 'w:gz') as archive:
        for relative in allowed:
            archive.add(SOURCE / relative, arcname='linuxcode/' + relative, recursive=False)
    temporary.rename(output)
    print(json.dumps({'package': str(output), 'sha256': sha(output), 'files': len(allowed),
                      'contains_apple_payloads': False}, indent=2))


def main():
    os.environ['PATH'] = os.environ.get('PATH', '') + ':/usr/local/sbin:/usr/sbin:/sbin'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path.home() / '.local/share/linuxcode/workspace')
    parser.add_argument('--state', type=Path, default=Path.home() / '.local/share/linuxcode/launcher')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('doctor'); p.add_argument('--report', type=Path)
    sub.add_parser('fetch', help='checkout and verify immutable milestone scripts')
    sub.add_parser('cache', help='download and verify base Linux/Darling assets')
    for name in ['setup', 'install-xcode']:
        p = sub.add_parser(name); p.add_argument('--xip', type=Path, required=True)
        p.add_argument('--sha256', help='expected SHA256 of locally supplied XIP')
    sub.add_parser('restore-sources', help='clone and apply the 17 locked source patches')
    sub.add_parser('adopt', help='validate and attach an already-built milestone candidate')
    sub.add_parser('status')
    sub.add_parser('recipe', help='show cold-build stages and exact outstanding gaps')
    p = sub.add_parser('package'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('dev', help='developer environment and module builds'); p.add_argument('argv', nargs=argparse.REMAINDER)
    p = sub.add_parser('xcodebuild'); p.add_argument('--dry-run', action='store_true'); p.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    workspace, state = args.workspace.expanduser().resolve(), args.state.expanduser().resolve()
    try:
        if args.command == 'doctor': return doctor(workspace, args)
        if args.command == 'fetch': fetch(workspace)
        elif args.command == 'cache': cache_assets(workspace)
        elif args.command == 'setup': setup(workspace, args)
        elif args.command == 'install-xcode': install_xcode(workspace, args.xip, args.sha256)
        elif args.command == 'restore-sources':
            verify_workspace(workspace)
            run([sys.executable, workspace / 'checkpoint/restore-sources.py', '--clone'], cwd=workspace)
            run([sys.executable, workspace / 'checkpoint/restore-sources.py', '--verify'], cwd=workspace)
        elif args.command == 'adopt': adopt(workspace, state)
        elif args.command == 'xcodebuild': return xcodebuild(state, args.argv, args.dry_run)
        elif args.command == 'dev':
            dev_args = args.argv[1:] if args.argv and args.argv[0] == '--' else args.argv
            return subprocess.run([sys.executable, str(SOURCE / 'dev/linuxcode-dev'),
                                   '--workspace', str(workspace), *dev_args]).returncode
        elif args.command == 'recipe': print((SOURCE / 'config/runtime-recipe.json').read_text())
        elif args.command == 'package': package(args.output)
        elif args.command == 'status':
            print(json.dumps({'workspace': str(workspace),
                'baseline_installed': (workspace / 'runtime/.installed').exists(),
                'xcode_installed': (workspace / 'runtime/state/prefix/Applications/Xcode.app').exists(),
                'adopted': json.loads((state / 'adopted.json').read_text()) if (state / 'adopted.json').exists() else None,
                'cold_milestone_install_ready': False, 'signed_build_ready': False}, indent=2))
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, KeyError, AssertionError) as error:
        print(f'linuxcode: {error}', file=sys.stderr)
        return 1
