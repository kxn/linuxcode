#!/usr/bin/env python3
"""Inspect actual UE iPhoneOS products and LocalMath linkage using host LLVM.

This reads build products; it does not build, sign, launch native code, or infer
successful linkage from build logs. Use the existing certificate-product tools
separately for original codesign and independent CMS verification.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def label(path):
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


class Inspection:
    def __init__(self, directory, record):
        self.directory = directory
        self.record = record

    def file(self, path):
        path = path.resolve(strict=True)
        require(path.is_file(), 'Not a regular file: ' + str(path))
        row = dict(path=label(path), bytes=path.stat().st_size, sha256=digest(path))
        self.record['files'][row['path']] = row
        return row

    def run(self, tool, *arguments):
        command = [tool, *map(str, arguments)]
        index = len(self.record['commands'])
        stdout = self.directory / f'{index:02d}.stdout'
        stderr = self.directory / f'{index:02d}.stderr'
        row = dict(argv=command, cwd=str(ROOT), status=None,
                   stdout=label(stdout), stderr=label(stderr))
        self.record['commands'].append(row)
        with stdout.open('xb') as out, stderr.open('xb') as err:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err,
                                    env={**os.environ, 'LC_ALL': 'C'}, timeout=120)
        row.update(status=result.returncode, stdout_sha256=digest(stdout),
                   stderr_sha256=digest(stderr), stdout_bytes=stdout.stat().st_size)
        require(result.returncode == 0, 'Host tool failed; see ' + label(stderr))
        return stdout.read_text(errors='replace')

    def macho(self, path, kind, tool):
        self.file(path)
        output = self.run(tool, '--file-headers', '--macho-version-min', path)
        cpus = re.findall(r'^\s*CpuType: (.+)$', output, re.M)
        kinds = re.findall(r'^\s*FileType: (\w+)', output, re.M)
        platforms = re.findall(r'^\s*Platform: (\S+)', output, re.M)
        require(cpus and all(cpu == 'Arm64 (0x100000C)' for cpu in cpus),
                'Expected only arm64 Mach-O input: ' + str(path))
        require(len(kinds) == len(cpus) and all(item == kind for item in kinds),
                'Unexpected Mach-O file type: ' + str(path))
        require(len(platforms) == len(cpus) and all(item == 'ios' for item in platforms),
                'Expected LC_BUILD_VERSION iPhoneOS, not simulator: ' + str(path))
        if kind == 'Executable':
            require(len(cpus) == 1, 'Expected one arm64 executable slice')
        return dict(verified=True, architecture='arm64', platform='iPhoneOS',
                    file_type=kind, Mach_O_members_or_slices=len(cpus))

    def symbols(self, path, tool, defined):
        output = self.run(tool, '--format=posix', '--no-demangle',
                          '--defined-only' if defined else '--undefined-only', path)
        types = '[TtWw]' if defined else 'U'
        matches = re.findall(r'^_local_add\s+' + types + r'\s+.*$', output, re.M)
        return dict(verified=bool(matches), symbol='_local_add', matches=matches)


def inspect(args, check, record):
    report = (ROOT / args.project_report).resolve(strict=True)
    check.file(report)
    preparation = json.loads(report.read_text())
    require(preparation.get('ordinary_UE_project_fixture') and
            preparation.get('fixture_authored_by_linuxcode'), 'Expected a UE fixture preparation report')
    project = (ROOT / (preparation.get('project') or preparation['directory'])).resolve(strict=True)
    target = preparation.get('target') or preparation['name']
    require(project.is_relative_to(ROOT / 'runtime'), 'UE fixture must be in runtime/')
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', target), 'Invalid fixture target')
    record.update(project=label(project), target=target, configuration=args.configuration)
    source_paths = [project / 'Source' / target / (target + suffix)
                    for suffix in ['.cpp', '.Build.cs']]
    source_paths += [project / 'Dependencies/LocalMath' / name
                     for name in ['LocalMath.c', 'LocalMath.h', 'LocalMath.podspec']]
    for path in source_paths:
        row = check.file(path)
        expected = preparation.get('files', {}).get(label(path))
        if expected:
            require(row['sha256'] == expected, 'Prepared source changed: ' + label(path))
    archive = (ROOT / args.archive).resolve(strict=True) if args.archive else (
        project / 'Intermediate/LinuxcodePods' / (args.configuration + '-iphoneos') /
        'libLocalMath.a').resolve(strict=True)
    record['pod_archive'] = dict(path=label(archive), **check.macho(archive, 'Relocatable', args.readobj))
    members = check.run(args.ar, 't', archive).splitlines()
    require('LocalMath.o' in members, 'Real LocalMath.o missing from Pod archive')
    record['pod_archive'].update(members=members, definition=check.symbols(archive, args.nm, True))
    require(record['pod_archive']['definition']['verified'], 'Pod archive does not define _local_add')
    record['pod_archive_verified'] = True
    if args.archive_only:
        record['scope'] = 'Pod archive and fixture sources only; App has not been checked'
        return

    app = (ROOT / args.app).resolve(strict=True)
    require(app.is_dir() and app.suffix == '.app', 'Expected an actual .app directory')
    info_path = app / 'Info.plist'
    check.file(info_path)
    info = plistlib.loads(info_path.read_bytes())
    executable = info.get('CFBundleExecutable', '')
    require(executable and Path(executable).name == executable and executable not in ['.', '..'],
            'Invalid CFBundleExecutable')
    require(executable == target or executable.startswith(target + '-'),
            'App executable does not belong to the prepared UE target')
    require(info.get('CFBundlePackageType') == 'APPL', 'Expected an application bundle')
    require(info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'], 'Expected iPhoneOS bundle')
    require(isinstance(info.get('CFBundleIdentifier'), str) and info['CFBundleIdentifier'],
            'Missing bundle identifier')
    binary = (app / executable).resolve(strict=True)
    require(binary.is_relative_to(app), 'Executable escapes App bundle')
    record['application'] = dict(path=label(app), executable=label(binary),
        bundle_identifier=info['CFBundleIdentifier'], minimum_OS=info.get('MinimumOSVersion'),
        **check.macho(binary, 'Executable', args.readobj))
    record['application']['pod_symbol'] = check.symbols(binary, args.nm, True)
    require(record['application']['pod_symbol']['verified'], 'Final executable does not define _local_add')
    record['full_app_product_verified'] = True

    objects = [(ROOT / name).resolve(strict=True) for name in args.module_object]
    if not objects:
        build = project / 'Intermediate/Build/IOS'
        objects = sorted(path.resolve() for path in build.glob(
            '**/' + args.configuration + '/' + target + '/*.o'))
    coverage = dict(verified=False, objects=[], unavailable_reason=None)
    for path in objects:
        row = check.file(path)
        # LLVM nm also understands LTO bitcode; unavailable symbols remain explicit.
        reference = check.symbols(path, args.nm, False)
        coverage['objects'].append(dict(**row, reference=reference))
        coverage['verified'] |= reference['verified']
    if objects:
        require(coverage['verified'], 'Module objects found but none reference _local_add')
    else:
        coverage['unavailable_reason'] = 'No module .o found; LTO or unavailable intermediate evidence is not verified'
    record['module_object_reference'] = coverage
    require(not args.require_module_reference or coverage['verified'], 'Module reference evidence is required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', help='Final built UE App; required unless --archive-only')
    parser.add_argument('--project-report', required=True, help='UE fixture preparation report')
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument('--report', help='New JSON report; existing reports are never overwritten')
    output.add_argument('--outdir', help='New evidence directory, containing result.json')
    parser.add_argument('--configuration', default='Development')
    parser.add_argument('--archive', help='Override the fixture configuration Pod archive path')
    parser.add_argument('--archive-only', action='store_true', help='Partial check while App is still building')
    parser.add_argument('--module-object', action='append', default=[])
    parser.add_argument('--require-module-reference', action='store_true')
    parser.add_argument('--nm', default='llvm-nm-19')
    parser.add_argument('--readobj', default='llvm-readobj-19')
    parser.add_argument('--ar', default='llvm-ar-19')
    args = parser.parse_args()
    if not args.app and not args.archive_only:
        parser.error('--app is required unless --archive-only is selected')
    if args.archive_only and (args.app or args.require_module_reference or args.module_object):
        parser.error('--archive-only cannot check App or module object evidence')
    if not re.fullmatch(r'[A-Za-z0-9_]+', args.configuration):
        parser.error('Invalid configuration name')
    destination = (ROOT / (args.outdir or args.report)).resolve()
    require(destination.is_relative_to(ROOT / 'runtime') or destination.is_relative_to(ROOT / 'artifacts'),
            'Write new reports under runtime/ or artifacts/')
    preparation = json.loads((ROOT / args.project_report).read_text())
    project = (ROOT / (preparation.get('project') or preparation['directory'])).resolve()
    require(not destination.is_relative_to(project), 'Keep verification reports outside the UE project')
    if args.app:
        require(not destination.is_relative_to((ROOT / args.app).resolve()), 'Keep reports outside the App')
    require(not destination.exists(), 'Output already exists: ' + str(destination))
    if args.outdir:
        destination.mkdir(parents=True)
        report = destination / 'result.json'
        evidence = destination
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = destination
        evidence = Path(tempfile.mkdtemp(prefix=report.stem + '-evidence-', dir=report.parent))
    record = dict(checked_at=datetime.now(timezone.utc).isoformat(), verified=False,
                  full_app_product_verified=False, pod_archive_verified=False,
                  scope='App, LocalMath archive and available UE module object linkage',
                  files={}, commands=[], source_sha256=digest(Path(__file__)),
                  signing_verified=False, device_execution_verified=False,
                  full_goal_complete=False, native_process_started=False)
    # Exclusive creation also protects against a concurrent verifier choosing this report.
    with report.open('x') as stream:
        try:
            for name in ['nm', 'readobj', 'ar']:
                tool = shutil.which(getattr(args, name))
                require(tool, 'Host LLVM tool unavailable: ' + getattr(args, name))
                setattr(args, name, tool)
            inspect(args, Inspection(evidence, record), record)
            for name, row in record['files'].items():
                require(digest(ROOT / name) == row['sha256'],
                        'Input changed during verification: ' + name)
            record['verified'] = True
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            record['error'] = str(error)
        stream.write(json.dumps(record, indent=2) + '\n')
    print(label(report))
    print('POD_ARCHIVE_ONLY_VERIFIED' if record['verified'] and args.archive_only else
          'UE_APP_AND_POD_PRODUCT_VERIFIED' if record['verified'] else 'VERIFICATION_FAILED')
    return 0 if record['verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
