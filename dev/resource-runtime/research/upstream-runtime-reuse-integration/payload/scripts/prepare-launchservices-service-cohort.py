#!/usr/bin/env python3
"""Prepare original LaunchServices jobs and a whole framework for a common run.

Host only. The generic stage-run-environment-launcher.py consumes the merged
cohort. Official LSRegisterURL initialization remains a separate runtime step;
this tool never constructs databases, edits type declarations or starts jobs.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    'usr/libexec/lsd',
    'usr/libexec/dirhelper',
    'System/Library/LaunchDaemons/com.apple.lsd.plist',
    'System/Library/LaunchAgents/com.apple.lsd.plist',
    'System/Library/LaunchDaemons/com.apple.bsd.dirhelper.plist',
]
FRAMEWORK = 'System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework'
XCODE_FILES = [
    'usr/libexec/configd', 'System/Library/LaunchDaemons/com.apple.configd.plist',
    'usr/libexec/diskarbitrationd', 'System/Library/LaunchDaemons/com.apple.diskarbitrationd.plist',
    'System/Library/CoreServices/coreservicesd', 'System/Library/LaunchDaemons/com.apple.coreservicesd.plist',
    'usr/sbin/filecoordinationd', 'System/Library/LaunchDaemons/com.apple.FileCoordination.plist',
]
CARBON_SUPPORT = 'System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/CarbonCore.framework/Versions/A/Support/coreservicesd'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def copy_runtime_framework(original, principal, output, inventory):
    """Preserve an entire original runtime bundle and its exact selected code."""
    base = principal.parents[2]
    assert principal.relative_to(base).as_posix() == 'Versions/A/' + base.stem
    before, existing = inventory(original), inventory(base)
    candidate = output / 'frameworks' / original.name
    shutil.copytree(original, candidate, symlinks=True, copy_function=shutil.copy2)
    main = 'Versions/A/' + original.stem
    for name, row in existing.items():
        if name == '.':
            continue
        source, target = base / name, candidate / name
        present = target.exists() or target.is_symlink()
        if name == main:
            assert source.is_file() and not source.is_symlink() and not target.is_symlink()
            shutil.copy2(source, target)
        elif present:
            assert before[name]['type'] == row['type'], name
            if row['type'] != 'directory':
                assert before[name] == row, name
        elif row['type'] == 'directory':
            target.mkdir(mode=row['mode'])
        elif row['type'] == 'symlink':
            target.symlink_to(row['target'])
        else:
            shutil.copy2(source, target)
    after = inventory(candidate)
    assert all(after[name] == row for name, row in before.items() if name != main)
    assert all(after[name] == row for name, row in existing.items() if row['type'] != 'directory')
    assert inventory(original) == before and inventory(base) == existing
    return candidate, dict(original=relative(original), original_inventory=before,
        candidate=relative(candidate), candidate_inventory=after,
        principal=relative(principal), principal_sha256=sha(principal), original_principal=before.get(main))


def provider_entry(destination, source, inventory):
    return dict(destination=destination, source=relative(source), files={
        name: dict(sha256=row['sha256']) if row['type'] == 'file' else dict(symlink=row['target'])
        for name, row in inventory(source).items() if row['type'] != 'directory'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--os-root', required=True)
    parser.add_argument('--expected-os-build', required=True)
    parser.add_argument('--parent-cohort', required=True)
    parser.add_argument('--parent-launcher-stage', required=True,
                        help='Exact parent image; needed for clone preimage validation')
    parser.add_argument('--current-principal', required=True,
                        help='Pinned currently selected .../Versions/A/LaunchServices')
    parser.add_argument('--reconstruction-report', required=True,
                        help='Existing whole-image proof matching the current principal SHA')
    parser.add_argument('--output-dir', required=True, help='New directory under runtime/')
    parser.add_argument('--xcode-build-services', action='store_true',
                        help='Also migrate the complete previously working configd/DA/CarbonCore/filecoordination chain')
    parser.add_argument('--framework-principals-file',
                        help='Explicit destination/source/SHA map of already-selected common framework principals')
    args = parser.parse_args()
    paths = {name: (ROOT / value).resolve(strict=True) for name, value in vars(args).items()
             if name not in ('expected_os_build', 'output_dir', 'xcode_build_services') and value is not None}
    assert all(path.is_relative_to(ROOT / 'runtime') for path in paths.values())
    output = (ROOT / args.output_dir).resolve()
    assert output.is_relative_to(ROOT / 'runtime') and not output.exists()
    helper = ROOT / 'scripts/prepare-security-framework-resources.py'
    spec = importlib.util.spec_from_file_location('whole_framework_inventory', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inventory = module.inventory

    os_root = paths['os_root']
    version_path = os_root / 'System/Library/CoreServices/SystemVersion.plist'
    os_info = plistlib.loads(version_path.read_bytes())
    assert os_info['ProductBuildVersion'] == args.expected_os_build
    parent_path = paths['parent_cohort']
    parent = json.loads(parent_path.read_text())
    assert parent['host_verified'] and not parent['installed']
    launcher = json.loads(paths['parent_launcher_stage'].read_text())
    image = launcher['materialized_shared_runtime']
    installed = image['service_cohort']
    assert installed['manifest_sha256'] == sha(parent_path)
    roots = {name: (ROOT / image[name]).resolve(strict=True)
             for name in ['whole_system_root', 'shared_prefix']}
    assert all(path.is_dir() and path.is_relative_to(ROOT / 'runtime') for path in roots.values())

    principal = paths['current_principal']
    base_framework = principal.parents[2]
    assert principal.relative_to(base_framework).as_posix() == 'Versions/A/LaunchServices'
    reconstruction = json.loads(paths['reconstruction_report'].read_text())
    assert sha(principal) == reconstruction['staged_image_sha256']
    original = os_root / FRAMEWORK
    original_inventory = inventory(original)
    base_inventory = inventory(base_framework)
    info = plistlib.loads((original / 'Resources/Info.plist').read_bytes())
    assert info['CFBundleIdentifier'] == 'com.apple.LaunchServices'
    declared = tuple(int(part) for part in info['CFBundleVersion'].split('.'))
    declared = (*declared, *(0 for _ in range(3-len(declared))))
    assert tuple(map(int, module.version(principal).split('.'))) == declared

    output.mkdir(parents=True, mode=0o755)
    candidate = output / 'frameworks/LaunchServices.framework'
    shutil.copytree(original, candidate, symlinks=True, copy_function=shutil.copy2)
    for name, entry in base_inventory.items():
        if name == '.':
            continue
        source, target = base_framework / name, candidate / name
        present = target.exists() or target.is_symlink()
        if name == 'Versions/A/LaunchServices':
            assert source.is_file() and not source.is_symlink()
            assert not target.is_dir() and not target.is_symlink()
            shutil.copy2(source, target)
        elif present:
            assert entry['type'] == original_inventory[name]['type'], name
            if entry['type'] != 'directory':
                assert original_inventory[name] == entry, name
        elif entry['type'] == 'directory':
            target.mkdir(mode=entry['mode'])
        elif entry['type'] == 'symlink':
            target.symlink_to(entry['target'])
        else:
            shutil.copy2(source, target)
    after = inventory(candidate)
    assert all(after[name] == entry for name, entry in original_inventory.items()
               if name != 'Versions/A/LaunchServices')
    assert all(after[name] == entry for name, entry in base_inventory.items()
               if entry['type'] != 'directory')
    assert inventory(original) == original_inventory
    assert inventory(base_framework) == base_inventory
    assert (candidate / 'Versions/Current').resolve(strict=True) == candidate / 'Versions/A'
    assert (candidate / 'Resources').resolve(strict=True) == candidate / 'Versions/A/Resources'
    assert (candidate / 'LaunchServices').resolve(strict=True) == candidate / 'Versions/A/LaunchServices'
    provider = dict(destination=FRAMEWORK, source=relative(candidate), files={
        name: dict(sha256=row['sha256']) if row['type'] == 'file' else dict(symlink=row['target'])
        for name, row in after.items() if row['type'] != 'directory'})
    (output / 'runtime-provider.json').write_text(json.dumps(provider, indent=2) + '\n')

    extra_providers, runtime_components = [], []
    if args.xcode_build_services:
        assert args.framework_principals_file
        choices = json.loads(paths['framework_principals_file'].read_text())
        required = {'System/Library/Frameworks/' + name + '.framework' for name in
                    ['SystemConfiguration', 'DiskArbitration', 'CoreServices']}
        required.add('System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/CarbonCore.framework')
        assert {row['destination'] for row in choices} == required
        for row in choices:
            source = (ROOT / row['source']).resolve(strict=True)
            assert source.is_relative_to(ROOT / 'runtime') and sha(source) == row['sha256']
            spelling = Path(row['destination'])
            assert not spelling.is_absolute() and '..' not in spelling.parts
            component, evidence = copy_runtime_framework(os_root / spelling, source, output, inventory)
            evidence.update(destination=row['destination'], MachO_current_version=module.version(source),
                original_bundle_version=plistlib.loads((os_root / spelling / 'Resources/Info.plist').read_bytes()).get('CFBundleVersion'))
            runtime_components.append(evidence)
            extra_providers.append(provider_entry(row['destination'], component, inventory))
        plugins = os_root / 'System/Library/SystemConfiguration'
        copied_plugins = output / 'runtime-data/SystemConfiguration'
        before_plugins = inventory(plugins)
        shutil.copytree(plugins, copied_plugins, symlinks=True, copy_function=shutil.copy2)
        assert inventory(copied_plugins) == before_plugins == inventory(plugins)
        runtime_components.append(dict(original=relative(plugins), original_inventory=before_plugins,
                                       candidate=relative(copied_plugins), candidate_inventory=before_plugins))
        extra_providers.append(provider_entry('System/Library/SystemConfiguration', copied_plugins, inventory))
    else:
        assert not args.framework_principals_file

    cohort = copy.deepcopy(parent)
    existing = {row['destination']: row for category in ['prefix_files', 'system_files']
                for row in parent[category]}
    assert len(existing) == len(parent['prefix_files']) + len(parent['system_files'])
    added, changed, preimages, registration, source_hashes = [], [], {}, [], {}
    source_origins = {}
    for name in [*FILES, *(XCODE_FILES if args.xcode_build_services else [])]:
        source, target = os_root / name, output / 'overlay' / name
        if name == 'System/Library/CoreServices/coreservicesd':
            # The extracted canonical entry is a zero-length placeholder.
            # Reuse the exact original counterpart previously executed by the
            # working CI, keeping the original launchd ProgramArguments path.
            assert source.is_file() and (source.stat().st_size == 0 or sha(source) == sha(os_root / CARBON_SUPPORT))
            source_origins[name] = dict(original_entry_sha256=sha(source), original_entry_size=source.stat().st_size,
                                        executable_source=CARBON_SUPPORT)
            source = os_root / CARBON_SUPPORT
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        assert source.is_file() and not source.is_symlink()
        assert not source.stat().st_mode & 0o7000
        original_sha = sha(source)
        shutil.copy2(source, target)
        assert sha(target) == sha(source) == original_sha
        source_hashes[name] = original_sha
        row = dict(destination=name, source=relative(target), sha256=original_sha,
                   original_Apple_service_or_plist=True)
        if name in existing:
            if existing[name]['sha256'] != original_sha:
                changed.append(name)
            cohort['system_files'] = [entry for entry in cohort['system_files'] if entry['destination'] != name]
            cohort['prefix_files'] = [entry for entry in cohort['prefix_files'] if entry['destination'] != name]
        else:
            added.append(name); changed.append(name)
            preimages[name] = {}
            for key, tree in roots.items():
                previous = tree / name
                assert not previous.is_symlink() and not previous.is_dir()
                preimages[name][key] = sha(previous) if previous.is_file() else None
        cohort['system_files'].append(row)
        if name.endswith('.plist'):
            job = plistlib.loads(source.read_bytes())
            assert not job.get('Disabled', False)
            assert not any(key.startswith(('DYLD_', 'DARLING_')) for key in job.get('EnvironmentVariables', {}))
            registration.append(dict(destination=name, **job))
    selected = {row['destination']: row for row in cohort.get('runtime_providers', [])}
    for row in [provider, *extra_providers]:
        selected[row['destination']] = row
    # A whole CoreServices bundle is installed before its explicitly selected
    # complete LS/CarbonCore children; every final principal remains unchanged.
    providers = sorted(selected.values(), key=lambda row: row['destination'].count('/'))
    cohort.update(host_verified=True, native_verified=False, installed=False, configuration_modified=False,
        derived_from=relative(parent_path), derived_from_sha256=sha(parent_path),
        clone_delta_files=changed, clone_additional_files=added, clone_new_entry_preimages=preimages,
        clone_delta_runtime_providers=[FRAMEWORK, *(row['destination'] for row in extra_providers)], runtime_providers=providers,
        all_programs_use_same_common_libraries=True, daemon_DYLD_overrides=False,
        addition='Original lsd and paired dirhelper with complete same-OS LaunchServices resources, using the unchanged common principal. Original argv, environment and account selection preserved.',
        LaunchServices_registration=registration, LaunchServices_native_startup_verified=False,
        xcode_complete_working_startup_chain=args.xcode_build_services)
    cohort_path = output / 'prepared-cohort.json'
    cohort_path.write_text(json.dumps(cohort, indent=2) + '\n')
    report = dict(host_verified=True, installed=False, native_execution=False,
        source_OS_build=args.expected_os_build, source_system_version=relative(version_path),
        source_system_version_sha256=sha(version_path), source_files=source_hashes,
        parent_cohort=relative(parent_path), parent_cohort_sha256=sha(parent_path),
        parent_launcher_stage=relative(paths['parent_launcher_stage']), parent_launcher_stage_sha256=sha(paths['parent_launcher_stage']),
        framework=relative(candidate), original_framework=relative(original),
        original_framework_inventory=original_inventory, candidate_inventory=after,
        original_principal=original_inventory.get('Versions/A/LaunchServices'),
        principal_source=relative(principal), principal_sha256=sha(principal),
        client_version=info['CFBundleVersion'], reconstruction_report=relative(paths['reconstruction_report']),
        reconstruction_report_sha256=sha(paths['reconstruction_report']),
        original_cache_image_sha256=reconstruction['original_image_sha256'],
        complete_xcode_service_chain=args.xcode_build_services, additional_runtime_components=runtime_components,
        canonical_original_entry_restorations=source_origins,
        registration=registration, prepared_cohort=relative(cohort_path), prepared_cohort_sha256=sha(cohort_path),
        source_bundles_unchanged=True, original_plists_unchanged=True, account_changes=False,
        manual_database_or_type_rows_created=False, source_algorithms_modified=False,
        excluded_service='launchservicesd (GUI/process-management closure not needed for this verified lsd/dirhelper chain)',
        installation_contract='Use the generic service-cohort stager before the first Mach-O. Select the same complete LS bundle in the common framework index and canonical tree. Afterwards use official LSRegisterURL on CoreTypes.bundle and Xcode.app; no per-process paths.',
        native_limit='Preparation and source hashes do not establish daemon startup, populated UTI database or API compatibility on a new cohort.',
        tool=relative(Path(__file__).resolve()), tool_sha256=sha(Path(__file__)),
        shared_inventory_helper=relative(helper), shared_inventory_helper_sha256=sha(helper))
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(relative(output / 'build.json'))


if __name__ == '__main__':
    main()
