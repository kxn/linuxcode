#!/usr/bin/env python3
"""Inventory the staged image superset in an observed resource-tool scope.

Diagnostic only. Scanning staged files includes images not actually loaded;
dlopen paths outside these directories and runtime symbol coalescing are not
inferred. Native tool execution remains the authority for the next failure.
"""
from pathlib import Path
import argparse
import hashlib
import json
import runpy
import subprocess
import sys

root = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    for path in [args.inventory, args.output]:
        assert not (root/path).exists(), 'Choose a fresh output: '+str(path)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    probe = json.loads((root/args.probe).read_text())
    scope = probe['scope']
    assert digest(root/scope['configuration']) == scope['configuration_sha256']
    assert not scope['original_tool_binaries_modified']
    env = scope['tool_environment']
    prefix = '/Volumes/SystemRoot/workspace/'
    Image = runpy.run_path(str(root/'scripts/audit-runtime-symbols.py'))['Image']
    stages = {}
    scanned, errors, absent = [], [], []
    seeds = set(scope['executables'])
    for key in ['DYLD_FRAMEWORK_PATH', 'DYLD_LIBRARY_PATH']:
        stages[key] = []
        for guest in env[key].split(':'):
            if not guest.startswith(prefix):
                continue
            path = root/guest.removeprefix(prefix)
            assert path.resolve().is_relative_to(root/'runtime')
            if not path.is_dir():
                absent.append(dict(variable=key, guest=guest))
                continue
            stages[key].append(path)
            paths = (sorted(f/f.name.removesuffix('.framework')
                            for f in path.glob('*.framework'))
                     if key == 'DYLD_FRAMEWORK_PATH' else sorted(path.glob('*.dylib')))
            for image in paths:
                if not image.is_file():
                    continue
                host = str(image.relative_to(root))
                try:
                    parsed = Image({'host': host})
                    name = parsed.install_name
                    assert name and name.startswith('/'), 'Nonabsolute install name'
                    seeds.add(name)
                    scanned.append(dict(host=host, install_name=name,
                                        sha256=parsed.host_sha256))
                except (AssertionError, ValueError, IndexError, KeyError) as error:
                    errors.append(dict(host=host, error=str(error)))
    command = [sys.executable, 'scripts/inventory-runtime-dependencies.py',
               '--runtime-root', str(args.runtime_root), '--output', str(args.inventory)]
    for seed in sorted(seeds):
        command += ['--seed', seed]
    for key, flag in [('DYLD_FRAMEWORK_PATH', '--framework-stage'),
                      ('DYLD_LIBRARY_PATH', '--library-stage')]:
        for stage in stages[key]:
            command += [flag, str(stage)]
    for guest in env['DYLD_LIBRARY_PATH'].split(':'):
        command += ['--library-path', guest]
    result = subprocess.run(command, cwd=root)
    sources = [Path(__file__), root/'scripts/inventory-runtime-dependencies.py',
               root/'scripts/audit-runtime-symbols.py', root/args.probe,
               root/scope['configuration']]
    report = dict(diagnostic_only=True, actual_loaded_image_set_verified=False,
                  scope_probe=str(args.probe), explicit_seed_count=len(seeds),
                  scanned_stage_images=scanned, scan_errors=errors,
                  absent_search_directories=absent,
                  command=command, inventory_returncode=result.returncode,
                  inventory=str(args.inventory),
                  sources={str(p.relative_to(root)): digest(p) for p in sources})
    if (root/args.inventory).exists():
        report['inventory_sha256'] = digest(root/args.inventory)
    with (root/args.output).open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
