#!/usr/bin/env python3
"""Run an existing isolated Unity export with one common runtime and fresh evidence.

The project, CI arguments, identity and DerivedData are reused. Every attempt
gets separate logs/results and independent signature verification. Preparation
never executes a macOS binary or changes the selected runtime configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import runpy
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def guest(path):
    return '/Volumes/SystemRoot/workspace/' + relative(path)


def runtime_path(name):
    path = (ROOT / name).resolve(strict=True)
    assert path.is_relative_to(ROOT / 'runtime')
    return path


def load_base(path):
    base = json.loads(path.read_text())
    folder = path.parent
    assert base['prepared'] and not base['native_execution']
    assert sha(ROOT / base['script']) == base['script_sha256']
    assert len(base['copied_source_inputs']) >= 7
    for name, digest in base['copied_source_inputs'].items():
        path_in_project = (folder / 'ios' / name).resolve(strict=True)
        assert path_in_project.is_relative_to(folder / 'ios')
        assert sha(path_in_project) == digest, name
    arguments = base['xcode_arguments']
    assert arguments[0] == '/usr/bin/xcodebuild' and arguments[-1] == 'build'
    assert arguments[arguments.index('-workspace') + 1] == guest(folder / 'ios/Unity-iPhone.xcworkspace')
    assert arguments[arguments.index('-derivedDataPath') + 1] == guest(folder / 'DerivedData')
    assert 'CODE_SIGNING_ALLOWED=YES' in arguments
    assert 'CODE_SIGN_IDENTITY=' + base['public_identity_SHA1'] in arguments
    store = runtime_path(base['identity_store'])
    assert store.is_file() and not store.stat().st_mode & 0o077
    der = store.parent / 'certificate.der'
    assert sha(der) == base['public_certificate_SHA256']
    assert hashlib.sha1(der.read_bytes()).hexdigest().upper() == base['public_identity_SHA1']
    return base


def product_hashes(base):
    result = {}
    for name in [base['application'], base['UnityFramework']]:
        product = (ROOT / name).resolve()
        assert product.is_relative_to(ROOT / 'runtime')
        info_path = product / 'Info.plist'
        if not info_path.is_file():
            result[relative(info_path)] = None
            continue
        info = plistlib.loads(info_path.read_bytes())
        executable = product / info['CFBundleExecutable']
        assert executable.resolve().is_relative_to(product)
        for path in [executable, product / 'Info.plist', product / '_CodeSignature/CodeResources']:
            if path.is_file():
                result[relative(path)] = sha(path)
    return result


def prepare(args):
    base_path = runtime_path(args.prepared)
    if base_path.is_dir():
        base_path /= 'prepared.json'
    base = load_base(base_path)
    configuration = (ROOT / args.configuration).resolve(strict=True)
    stage = (ROOT / args.stage).resolve(strict=True)
    assert configuration.is_relative_to(ROOT) and stage.is_relative_to(ROOT)
    assert json.loads(configuration.read_text())['runtime_mode'] == 'unified'
    folder = Path(tempfile.mkdtemp(prefix='unity-prepared-build-attempt-', dir=ROOT / 'runtime'))
    folder.chmod(0o700)
    script = folder / 'run.sh'
    script.write_bytes((ROOT / base['script']).read_bytes())
    old_result = base_path.parent / 'result.json'
    report = dict(prepared=True, native_execution=False,
        base_prepared=relative(base_path), base_prepared_sha256=sha(base_path),
        configuration=relative(configuration), configuration_sha256=sha(configuration),
        stage=relative(stage), stage_sha256=sha(stage), script=relative(script), script_sha256=sha(script),
        base_result=relative(old_result) if old_result.is_file() else None,
        base_result_sha256=sha(old_result) if old_result.is_file() else None,
        xcode_arguments=base['xcode_arguments'], derived_data_reused=True,
        copied_project_or_cache=False, product_hashes_before=product_hashes(base),
        public_identity_SHA1=base['public_identity_SHA1'], public_certificate_SHA256=base['public_certificate_SHA256'],
        tool=relative(Path(__file__).resolve()), tool_sha256=sha(Path(__file__)),
        run_command=['python3', relative(Path(__file__).resolve()), '--attempt', relative(folder), '--timeout', str(args.timeout)],
        limits='Existing Linux Unity export and compiled cache. This is not a fresh Mac Unity export or a cold compilation; actual per-task counts are recorded.')
    (folder / 'prepared.json').write_text(json.dumps(report, indent=2) + '\n')
    return folder


def execute(folder, timeout):
    prepared_path = folder / 'prepared.json'
    prepared = json.loads(prepared_path.read_text())
    assert not (folder / 'result.json').exists(), 'Use a fresh attempt; never overwrite prior results'
    assert sha(Path(__file__)) == prepared['tool_sha256']
    for name in ['configuration', 'stage', 'script', 'base_prepared']:
        assert sha(ROOT / prepared[name]) == prepared[name + '_sha256'], name
    base = load_base(ROOT / prepared['base_prepared'])
    module = runpy.run_path(str(ROOT / 'scripts/direct-resource-tool-runtime-profile.py'))
    profile = module['profile'](stage=prepared['stage'], configuration=prepared['configuration'])
    assert profile['direct_resource_environment']['runtime_mode'] == 'unified'
    command = list(profile['command'][:-2])
    assert not any(value.startswith('DARLING_DYLD_OVERRIDE_') for value in command)
    identity = 'LINUXCODE_IDENTITY_STORE=' + guest(runtime_path(base['identity_store']))
    positions = [i for i, value in enumerate(command) if value.startswith('LINUXCODE_IDENTITY_STORE=')]
    assert len(positions) <= 1
    if positions:
        command[positions[0]] = identity
    else:
        command.append(identity)
    command += ['/bin/bash', guest(ROOT / prepared['script'])]
    command[3] = str(timeout)
    record = dict(verified=False, native_execution=True, prepared_sha256=sha(prepared_path),
        configuration=prepared['configuration'], stage=prepared['stage'], command=command,
        source_runtime=profile['source_runtime'], source_sha256=sha(Path(__file__)),
        xcode_arguments=base['xcode_arguments'], derived_data_reused=True,
        public_identity_SHA1=base['public_identity_SHA1'], public_certificate_SHA256=base['public_certificate_SHA256'],
        original_Mac_Unity_export_verified=False, developer_provisioning_or_device_trust_verified=False,
        limits=prepared['limits'])
    print('RUNNING', relative(folder), flush=True)
    start = time.monotonic()
    with (folder / 'run.log').open('w') as stream:
        result = subprocess.run(command, cwd=ROOT, env=module['environment'](profile), stdout=stream, stderr=subprocess.STDOUT)
    text = (folder / 'run.log').read_text(errors='replace')
    record.update(outer_status=result.returncode, elapsed_seconds=time.monotonic()-start,
        log=relative(folder / 'run.log'), log_sha256=sha(folder / 'run.log'))
    statuses = {name: re.findall(r'^' + marker + r' (-?\d+)$', text, re.M)
                for name, marker in [('build', 'UNITY_UNIFIED_BUILD_STATUS'),
                                     ('App_strict', 'UNITY_UNIFIED_APP_STRICT_STATUS'),
                                     ('Framework_strict', 'UNITY_UNIFIED_FRAMEWORK_STRICT_STATUS')]}
    record['native_statuses'] = statuses
    tasks = ['CompileC', 'SwiftCompile', 'SwiftEmitModule', 'Ld', 'Libtool', 'CodeSign',
             'PhaseScriptExecution', 'CompileAssetCatalog', 'CompileStoryboard', 'CompileXIB']
    record['actual_task_counts'] = {name: len(re.findall(r'^' + name + r'\s', text, re.M)) for name in tasks}
    record['actual_sign_commands'] = [line.strip() for line in text.splitlines()
                                      if re.match(r'\s*/usr/bin/codesign\s', line)]
    record['synthetic_identity_seen_in_sign_command'] = any(base['public_identity_SHA1'] in line
                                                          for line in record['actual_sign_commands'])
    passed = result.returncode == 0 and all(value == ['0'] for value in statuses.values()) and '** BUILD SUCCEEDED **' in text
    if passed:
        verify = list(base['independent_verify_command'])
        assert verify[:2] == ['python3', 'scripts/verify-native-certificate-products.py']
        verify[verify.index('--report') + 1] = relative(folder / 'independent-products.json')
        with (folder / 'independent-verification.log').open('w') as stream:
            check = subprocess.run(verify, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        record['independent_verify_command'] = verify
        record['independent_verify_status'] = check.returncode
        symbol_check = subprocess.run(['llvm-nm-19', '--defined-only', str(ROOT / base['UnityFramework'] / 'UnityFramework')],
                                      capture_output=True, text=True)
        record['native_Pod_symbol_defined'] = symbol_check.returncode == 0 and bool(re.search(
            r'\b' + re.escape(base['native_Pod_symbol_required']) + r'$', symbol_check.stdout, re.M))
        record['verified'] = check.returncode == 0 and record['native_Pod_symbol_defined']
        if check.returncode == 0:
            independent = json.loads((folder / 'independent-products.json').read_text())
            record['current_certificate_bound_to_products'] = independent['verified'] and independent['public_certificate_SHA256'] == base['public_certificate_SHA256']
            record['verified'] = record['verified'] and record['current_certificate_bound_to_products']
    record['product_hashes_before'] = prepared['product_hashes_before']
    record['product_hashes_after'] = product_hashes(base)
    record['original_project_inputs_unchanged'] = all(
        (ROOT / base['source_run'] / 'ios' / name).is_file() and
        sha(ROOT / base['source_run'] / 'ios' / name) == digest for name, digest in base['copied_source_inputs'].items())
    record['base_project_inputs_unchanged'] = all(
        ((ROOT / prepared['base_prepared']).parent / 'ios' / name).is_file() and
        sha((ROOT / prepared['base_prepared']).parent / 'ios' / name) == digest for name, digest in base['copied_source_inputs'].items())
    record['base_result_preserved'] = not prepared['base_result'] or sha(ROOT / prepared['base_result']) == prepared['base_result_sha256']
    record['verified'] = record['verified'] and all(record[key] for key in [
        'original_project_inputs_unchanged', 'base_project_inputs_unchanged', 'base_result_preserved'])
    (folder / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print('EVIDENCE', relative(folder / 'result.json'))
    return 0 if record['verified'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--prepared', help='Existing project preparation JSON or its directory')
    choice.add_argument('--attempt', help='Previously prepared fresh attempt directory')
    parser.add_argument('--configuration')
    parser.add_argument('--stage')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    assert 10 <= args.timeout <= 7200
    if args.attempt:
        assert not any([args.configuration, args.stage, args.prepare_only])
        folder = runtime_path(args.attempt)
    else:
        assert args.configuration and args.stage
        folder = prepare(args)
        print('PREPARED', relative(folder), flush=True)
        if args.prepare_only:
            return 0
    return execute(folder, args.timeout)


if __name__ == '__main__':
    raise SystemExit(main())
