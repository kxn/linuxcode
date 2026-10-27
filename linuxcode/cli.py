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


def candidate(workspace, native=None):
    engine = native and native.get('engine_milestone')
    certificate = native and native.get('certificate_candidate')
    if certificate:
        from linuxcode.certificates import candidate as certificate_candidate
        helper = workspace / 'scripts/verified-file-digest.py'
        digest = runpy.run_path(str(helper))['digest'] if helper.exists() else sha
        module, profile, record = certificate_candidate(workspace, native, digest)
        report_path = workspace / native['build_report']
    elif engine:
        milestone = json.loads((workspace / engine).read_text())
        if (not milestone['verified'] or not milestone['original_xcodebuild_full_build_and_original_codesign_success']
                or not milestone['ad_hoc_signing_only'] or milestone['zsign_used']):
            fail('Engine milestone does not record a successful original signed build.')
        report_path = workspace / native['build_report']
        if (milestone['build_report'] != native['build_report']
                or milestone['build_report_sha256'] != sha(report_path)):
            fail('Engine build evidence changed.')
        signed_path = workspace / milestone['signature_report']
        signed = json.loads(signed_path.read_text())
        if (sha(signed_path) != milestone['signature_report_sha256'] or not signed['verified']
                or not signed['ad_hoc_only'] or signed['zsign_used']
                or signed['stage'] != milestone['stage']
                or signed['configuration'] != milestone['resource_environment']
                or signed['outer_status'] != 0 or len(signed['native_statuses']) != 6
                or any(status != '0' for index, status in signed['native_statuses'])
                or not all(value['verified'] for value in signed['independent_checks'].values())):
            fail('Engine product signatures do not match the successful candidate.')
        if sha(workspace / signed['log']) != signed['log_sha256']:
            fail('Engine signature verification log changed.')
        for name, evidence in milestone['file_evidence'].items():
            if sha(workspace / name) != evidence['sha256']:
                fail('Engine product changed: ' + name)
        module = runpy.run_path(str(workspace / 'scripts/direct-resource-tool-runtime-profile.py'))
        profile = module['profile'](stage=milestone['stage'], configuration=milestone['resource_environment'])
        if profile['source_runtime'] != signed['source_runtime']:
            fail('Engine signature checks selected different source components.')
        if sha(workspace / native['prebuild_file']) != native['prebuild_sha256']:
            fail('Engine service prelude changed.')
    elif native:
        module = runpy.run_path(str(workspace / 'scripts/native-codesign-runtime-profile.py'))
        profile = module['profile'](native_codesign_stage=native['stage'],
                                   identity_store=native['identity_store'], diagnostic=True)
        report_path = workspace / native['build_report']
        signed = json.loads((workspace / native['product_report']).read_text())
        if (not signed['verified'] or signed['zsign_used'] or not signed['ad_hoc_only']
                or signed['build_report'] != native['build_report']
                or signed['build_report_sha256'] != sha(report_path)
                or signed['native_codesign_stage'] != native['stage']
                or signed['stage_sha256'] != sha(workspace / native['stage'])
                or signed['native_product_statuses'] != [['0', '0'], ['1', '0'], ['2', '0']]):
            fail('Native signing evidence does not match this successful ad-hoc candidate.')
        for name, digest in {**signed['files'], signed['log']: signed['log_sha256']}.items():
            if sha(workspace / name) != digest:
                fail('Native signing evidence changed: ' + name)
        for name, attributes in signed['archive_signature_attributes'].items():
            for attribute, digest in attributes.items():
                if hashlib.sha256(os.getxattr(workspace / name, attribute)).hexdigest() != digest:
                    fail('Native archive signature attribute changed: ' + name)
    else:
        module = runpy.run_path(str(workspace / LOCK['candidate']['profile']))
        profile = module['profile'](diagnostic=True)
        report_path = workspace / LOCK['candidate']['report']
    record = json.loads(report_path.read_text())
    if record['exit_status'] != 0 or not record['xcode_process_returned']:
        fail('Candidate evidence does not record successful native return.')
    if sha(workspace / record['log']) != record['log_sha256']:
        fail('Candidate success log checksum changed.')
    text = (workspace / record['log']).read_text()
    success_marker = 'ARCHIVE SUCCEEDED' if record.get('xcode_arguments', [])[-1:] == ['archive'] else 'BUILD SUCCEEDED'
    if success_marker not in text or not re.search(r'^SERVICE_RUNTIME_XCODE_STATUS 0$', text, re.M):
        fail('Candidate log does not contain the successful native build status.')
    if record['source_runtime'] != profile['source_runtime']:
        fail('Candidate evidence and runtime profile do not select identical source components.')
    if native and record.get('native_codesign_stage') != native['stage']:
        fail('Native signing stage differs from the actual Xcode build evidence.')
    if engine and record.get('private_procfs_stage') != milestone['stage']:
        fail('Engine runtime stage differs from the actual Xcode build evidence.')
    if sha(workspace / 'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild') != LOCK['xcode']['xcodebuild_sha256']:
        fail('Installed original xcodebuild differs from the locked milestone.')
    for job in record['jobs']:
        if sha(workspace / job['path']) != job['sha256']:
            fail('Recorded service job changed: ' + job['path'])
    return module, profile, record


def adopt(workspace, state, native=None):
    _, profile, record = candidate(workspace, native=native) if native else candidate(workspace)
    state.mkdir(parents=True, exist_ok=True)
    save(state / 'adopted.json', {'workspace': str(workspace),
         'source_runtime': profile['source_runtime'],
         'evidence_report_sha256': sha(workspace / (native['build_report'] if native else LOCK['candidate']['report'])),
         'native_candidate': native, 'diagnostic_policy': True,
         'signed_builds_ready': bool(native), 'signing_scope': 'certificate' if native and native.get('certificate_candidate') else 'ad-hoc' if native else 'unsigned',
         'certificate_signing_ready': bool(native and native.get('certificate_candidate')),
         'developer_provisioning_or_device_trust_verified': False})
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
    native = adopted.get('native_candidate')
    module, profile, record = candidate(workspace, native=native) if native else candidate(workspace)
    if profile['source_runtime'] != adopted['source_runtime']:
        fail('Adopted runtime changed; inspect and adopt again.')
    if sha(workspace / (native['build_report'] if native else LOCK['candidate']['report'])) != adopted['evidence_report_sha256']:
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
            'diagnostic_policy': True, 'signing_ready': bool(native),
            'signing_scope': adopted.get('signing_scope', 'ad-hoc' if native else 'unsigned'), 'headless': True,
            'certificate_signing_ready': bool(native and native.get('certificate_candidate')),
            'developer_provisioning_or_device_trust_verified': False, 'timeout_seconds': timeout_seconds}
    bindings = os.environ.get('LINUXCODE_WORKSPACE_BINDINGS')
    if bindings:
        if not profile.get('workspace_bind_stage'):
            fail('This candidate does not support private workspace mappings.')
        bindings = Path(bindings).resolve(strict=True)
        if not bindings.is_relative_to(workspace / 'runtime'):
            fail('Workspace mappings must be configured inside the workspace runtime directory.')
        plan['workspace_bindings'] = {'path': str(bindings.relative_to(workspace)), 'sha256': sha(bindings)}
    if dry_run:
        return plan, None, None
    invocation = workspace / 'runtime/linuxcode-cli' / (time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8])
    invocation.mkdir(parents=True)
    certificate = native and native.get('certificate_candidate')
    signing = {}
    if certificate:
        helper = runpy.run_path(str(workspace / 'scripts/native-certificate-runtime.py'))
        profile = helper['prepare_services'](profile, invocation / 'signing-services')
        signing = profile['native_certificate_runtime']
        plan['certificate_runtime'] = signing
    jobs = []
    for index, existing in enumerate(record['jobs']):
        job = dict(existing['job'])
        job['EnvironmentVariables'] = dict(job['EnvironmentVariables'])
        if certificate:
            for value in profile['command']:
                if value.startswith(('DYLD_LIBRARY_PATH=', 'DYLD_FRAMEWORK_PATH=', 'LINUXCODE_IDENTITY_STORE=')):
                    key, setting = value.split('=', 1)
                    job['EnvironmentVariables'][key] = setting
        job['StandardOutPath'] = job['StandardErrorPath'] = GUEST + str((invocation / f'service-{index}.log').relative_to(workspace))
        path = invocation / f'service-{index}.plist'
        path.write_bytes(plistlib.dumps(job))
        path.chmod(0o644)
        session = '-S Background ' if existing['name'] in ['distnoted-agent', 'cfprefsd-agent'] else ''
        jobs.append((job['Label'], GUEST + str(path.relative_to(workspace)), session))
    script = invocation / 'run.sh'
    prebuild = ''
    if native and (native.get('engine_milestone') or certificate):
        prebuild_argv = json.loads((workspace / native['prebuild_file']).read_text())
        if not isinstance(prebuild_argv, list) or not prebuild_argv or not all(isinstance(v, str) for v in prebuild_argv):
            fail('Engine service prelude must contain a command argument list.')
        prebuild = shlex.join(prebuild_argv) + '\n'
    script.write_text('#!/bin/bash\nset -e\nunset DISPLAY WAYLAND_DISPLAY XAUTHORITY\nloaded=()\n' +
        'cleanup() { local i; for ((i=${#loaded[@]}-1; i>=0; i--)); do launchctl remove "${loaded[$i]}" >/dev/null 2>&1 || true; done; ' + (signing['cleanup'] + ' || true; ' if signing else '') + '}\ntrap cleanup EXIT\n' +
        signing.get('startup', '') +
        'launchctl remove com.apple.FileCoordination >/dev/null 2>&1 || true\n' +
        '\n'.join('launchctl load ' + session + shlex.quote(path) + '\nloaded+=(' + shlex.quote(label) + ')' for label, path, session in jobs) + '\n' +
        "printf 'LINUXCODE_SERVICES_LOADED\\n'\n" +
        prebuild + 'cd ' + shlex.quote(cwd) + '\nset +e\n' +
        '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild "$@"\n' +
        'status=$?\nprintf "LINUXCODE_NATIVE_XCODE_STATUS %s\\n" "$status"\nexit "$status"\n')
    command = profile['command'][:-2] + ['/bin/bash', GUEST + str(script.relative_to(workspace)), *mapped]
    # Preserve the verified launcher environment, with an explicit long build budget.
    command[3] = str(timeout_seconds)
    save(invocation / 'plan.json', plan)
    environment = module['environment'](profile)
    if bindings:
        environment['LINUXCODE_WORKSPACE_BINDINGS'] = str(bindings)
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
        environment.pop(name, None)
    return plan, invocation, (command, environment)


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


def package(output, include_research_history=True):
    allowed = ['linuxcode.py', 'linuxcode/cli.py', 'linuxcode/certificates.py', 'linuxcode/identities.py', 'linuxcode/__init__.py',
               'config/dependencies.lock.json', 'config/runtime-recipe.json',
               'README.md', 'docs/install.md', 'docs/runtime-inputs.md', 'LICENSE', '.gitignore',
               'validation/2026-10-19.json',
               'validation/unity-signed-app-2026-10-27.json',
               'validation/original-certificate-app-2026-10-27.json',
               'validation/unity-certificate-ci-2026-10-27.json',
               'tests/test_installer.py', 'tests/test_engine_candidate.py', 'tests/test_certificate_candidate.py', 'tests/test_identity_import.py', 'dev/linuxcode-dev', 'dev/README.md',
               'dev/debian-packages.txt', 'dev/locks/developer.lock.json',
               'dev/locks/source-manifest.json']
    resource = 'dev/resource-runtime/'
    overlay = json.loads((SOURCE / resource / 'overlay.json').read_text())
    allowed += [resource + name for name in ('README.md', 'apply-overlay.py',
        'build-resources.py', 'overlay.json', 'evidence/summary.json', 'tests/test_overlay.py')]
    for relative, entry in overlay['files'].items():
        name = Path(relative)
        if name.is_absolute() or '..' in name.parts or name.suffix not in ('.py', '.json', '.swift', '.c', '.rb'):
            fail('Invalid developer source payload path: ' + relative)
        payload = resource + 'payload/' + relative
        if sha(SOURCE / payload) != entry['sha256']:
            fail('Developer source payload checksum mismatch: ' + relative)
        allowed.append(payload)
    for relative, digest in overlay.get('research_files', {}).items():
        # Public installers retain developer sources and README files. The
        # large historical diagnostics are an explicit CLI opt-in.
        if not include_research_history and '/reference/' in relative:
            continue
        name = Path(relative)
        if (name.is_absolute() or '..' in name.parts or name.parts[0] != 'research'
                or (name.suffix not in ('.py', '.json', '.m', '.mm', '.c', '.h', '.cpp', '.hpp', '.md', '.swift', '.cs', '.rb', '.S', '.s', '.inc')
                    and name.name not in ('CMakeLists.txt', 'pthread.aliases', 'syscalls.master')
                    and not name.name.endswith(('.h.in', '.exp-in')))):
            fail('Invalid research source path: ' + relative)
        source = resource + relative
        if sha(SOURCE / source) != digest:
            fail('Research source checksum mismatch: ' + relative)
        allowed.append(source)
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
    p = sub.add_parser('adopt', help='validate and attach an already-built milestone candidate')
    p.add_argument('--engine-milestone', type=Path, help='adopt a verified original Unity/CocoaPods build and its matching runtime')
    p.add_argument('--certificate-candidate', type=Path, help='adopt a verified certificate runtime with a caller-supplied identity store')
    p.add_argument('--native-codesign-stage', type=Path)
    p.add_argument('--identity-store', type=Path)
    p.add_argument('--build-report', type=Path)
    p.add_argument('--product-report', type=Path)
    sub.add_parser('status')
    p = sub.add_parser('import-identity', help='import a caller P12 into a private read-only RSA identity store')
    p.add_argument('--p12', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--password-env', required=True); p.add_argument('--label', default='CI signing identity')
    p.add_argument('--certificate-sha256'); p.add_argument('--legacy', action='store_true')
    sub.add_parser('recipe', help='show cold-build stages and exact outstanding gaps')
    p = sub.add_parser('package'); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--include-research-history', action='store_true', help='also bundle historical diagnostic attachments')
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
        elif args.command == 'import-identity':
            from linuxcode.identities import import_p12
            print(json.dumps(import_p12(workspace,args.p12,args.output,args.password_env,args.label,args.certificate_sha256,args.legacy),indent=2))
        elif args.command == 'restore-sources':
            verify_workspace(workspace)
            run([sys.executable, workspace / 'checkpoint/restore-sources.py', '--clone'], cwd=workspace)
            run([sys.executable, workspace / 'checkpoint/restore-sources.py', '--verify'], cwd=workspace)
        elif args.command == 'adopt':
            native = None
            choices = [args.native_codesign_stage, args.identity_store, args.build_report, args.product_report]
            if args.certificate_candidate:
                if args.engine_milestone or args.native_codesign_stage or args.build_report or args.product_report or not args.identity_store:
                    fail('Certificate adoption requires only a certificate candidate and an identity store.')
                path = (workspace / args.certificate_candidate).resolve().relative_to(workspace)
                cert = json.loads((workspace / path).read_text())
                build_path = cert['verified_build']['build_report']['path']
                build = json.loads((workspace / build_path).read_text())
                prebuild = build['probe_configuration']['prebuild_command_file']
                native = dict(certificate_candidate=str(path), candidate_sha256=sha(workspace / path),
                              identity_store=str((workspace / args.identity_store).resolve().relative_to(workspace)),
                              build_report=build_path, stage=build['native_codesign_stage'],
                              prebuild_file=prebuild, prebuild_sha256=sha(workspace / prebuild))
            elif args.engine_milestone:
                if any(choices): fail('Engine milestone adoption cannot be combined with native candidate options.')
                milestone_path = (workspace / args.engine_milestone).resolve().relative_to(workspace)
                milestone = json.loads((workspace / milestone_path).read_text())
                build = json.loads((workspace / milestone['build_report']).read_text())
                prebuild = build['probe_configuration']['prebuild_command_file']
                native = dict(engine_milestone=str(milestone_path), build_report=milestone['build_report'],
                              stage=build['native_codesign_stage'], prebuild_file=prebuild,
                              prebuild_sha256=sha(workspace / prebuild))
            elif any(choices):
                if not all(choices): fail('Native adoption requires stage, identity store, build report and product report.')
                native = {key: str((workspace / path).resolve().relative_to(workspace)) for key, path in zip(
                    ['stage', 'identity_store', 'build_report', 'product_report'], choices)}
            adopt(workspace, state, native)
        elif args.command == 'xcodebuild': return xcodebuild(state, args.argv, args.dry_run)
        elif args.command == 'dev':
            dev_args = args.argv[1:] if args.argv and args.argv[0] == '--' else args.argv
            return subprocess.run([sys.executable, str(SOURCE / 'dev/linuxcode-dev'),
                                   '--workspace', str(workspace), *dev_args]).returncode
        elif args.command == 'recipe': print((SOURCE / 'config/runtime-recipe.json').read_text())
        elif args.command == 'package': package(args.output, include_research_history=args.include_research_history)
        elif args.command == 'status':
            adopted = json.loads((state / 'adopted.json').read_text()) if (state / 'adopted.json').exists() else None
            print(json.dumps({'workspace': str(workspace),
                'baseline_installed': (workspace / 'runtime/.installed').exists(),
                'xcode_installed': (workspace / 'runtime/state/prefix/Applications/Xcode.app').exists(),
                'adopted': adopted,
                'cold_milestone_install_ready': False,
                'signed_build_ready': bool(adopted and adopted.get('signed_builds_ready')),
                'signing_scope': adopted.get('signing_scope', 'unsigned') if adopted else None,
                'certificate_signing_ready': bool(adopted and adopted.get('certificate_signing_ready')),
                'developer_provisioning_or_device_trust_verified': False}, indent=2))
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, KeyError, AssertionError) as error:
        print(f'linuxcode: {error}', file=sys.stderr)
        return 1
