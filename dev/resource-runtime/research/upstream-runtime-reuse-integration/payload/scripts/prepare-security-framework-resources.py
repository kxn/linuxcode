#!/usr/bin/env python3
"""Prepare a new Security framework with an immutable, version-matched OS resource cohort.

Host-only preparation: no runtime indexes, old bundles or installed roots change.
The caller installs the same output bundle at the shared and canonical paths.
"""
from pathlib import Path
import argparse, hashlib, json, os, plistlib, shutil, stat, struct, subprocess

root = Path(__file__).resolve().parent.parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def relative(path):
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)

def version(image):
    data = image.read_bytes()
    assert struct.unpack_from('<I', data)[0] == 0xfeedfacf, image
    offset = 32
    values = []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        assert size >= 8 and offset + size <= len(data)
        if command == 13:
            value = struct.unpack_from('<I', data, offset + 16)[0]
            values.append(f'{value >> 16}.{(value >> 8) & 255}.{value & 255}')
        offset += size
    assert len(values) == 1, image
    return values[0]

def inventory(directory):
    entries = {}
    for path in [directory, *sorted(directory.rglob('*'))]:
        name = '.' if path == directory else str(path.relative_to(directory))
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            assert path.resolve().is_relative_to(directory.resolve()), path
            entries[name] = dict(type='symlink', target=os.readlink(path), mode=mode)
        elif path.is_dir():
            entries[name] = dict(type='directory', mode=mode)
        else:
            assert path.is_file(), path
            entries[name] = dict(type='file', mode=mode, size=path.stat().st_size, sha256=sha(path))
    return entries

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-build', required=True, help='Sealed common Security build report')
    p.add_argument('--resource-root', required=True, help='Resources directory from the OS image')
    p.add_argument('--source-system-version', required=True, help='Same OS image SystemVersion.plist')
    p.add_argument('--original-image', required=True, help='Unmodified extracted cache Security image')
    p.add_argument('--reconstruction-report', required=True)
    p.add_argument('--expected-os-build', required=True)
    p.add_argument('--output-dir', required=True, help='New, nonexistent directory under runtime/')
    p.add_argument('--whole-framework', action='store_true', help='Preserve the complete OS framework, overlaying only the sealed common binary and missing base entries')
    a = p.parse_args()
    paths = {key: (root / value).resolve() for key, value in vars(a).items() if key not in ('expected_os_build', 'whole_framework')}
    assert all(path.is_relative_to(root) for path in paths.values())
    output = paths['output_dir']
    assert output.is_relative_to(root / 'runtime') and not output.exists(), output
    base_report = json.loads(paths['base_build'].read_text())
    binary = root / base_report['framework']
    assert sha(binary) == base_report['files'][base_report['framework']]
    framework = binary.parents[2]
    assert binary.relative_to(framework) == Path('Versions/A/Security')
    resource = paths['resource_root']
    system_version = paths['source_system_version']
    os_root = system_version.parents[3]
    assert system_version.relative_to(os_root) == Path('System/Library/CoreServices/SystemVersion.plist')
    assert resource.relative_to(os_root) == Path('System/Library/Frameworks/Security.framework/Versions/A/Resources')
    os_info = plistlib.loads(system_version.read_bytes())
    assert os_info['ProductBuildVersion'] == a.expected_os_build
    bundle_info = plistlib.loads((resource / 'Info.plist').read_bytes())
    assert bundle_info['CFBundleIdentifier'] == 'com.apple.security'
    bundle_version = bundle_info['CFBundleVersion']
    assert version(binary) == version(paths['original_image']) == bundle_version
    reconstruction = json.loads(paths['reconstruction_report'].read_text())
    assert sha(paths['original_image']) == reconstruction['original_image_sha256']
    assert sha(root / base_report['base']) == reconstruction['staged_image_sha256']
    entries = inventory(resource)
    # Only OS framework contents are accepted, never a user's keychain/export.
    forbidden_suffixes = {'.p12', '.pfx', '.key', '.keychain', '.keychain-db'}
    for name, entry in entries.items():
        if entry['type'] != 'file':
            continue
        path = resource / name
        assert path.suffix.lower() not in forbidden_suffixes, name
        assert b'PRIVATE KEY-----' not in path.read_bytes(), name
    db_headers = {}
    for name in ['mdsObject.db', 'mdsDirectory.db']:
        data = (resource / name).read_bytes()
        magic, db_version, auth_offset, schema_offset = struct.unpack_from('>4I', data)
        assert magic == 0x6b796368 and db_version == 0x10000
        assert 16 <= auth_offset <= schema_offset < len(data) - 4
        db_headers[name] = dict(format='Apple FileDL/MDS kych', byte_order='big',
            version=db_version, auth_offset=auth_offset, schema_offset=schema_offset,
            trailer_version=struct.unpack_from('>I', data, len(data) - 4)[0],
            size=len(data), sha256=sha(resource / name), private_key_database=False)
    before = inventory(framework)
    output.mkdir()
    candidate = output / 'frameworks/Security.framework'
    source_framework = resource.parents[2]
    source_inventory = inventory(source_framework) if a.whole_framework else None
    base_additions = []
    if a.whole_framework:
        shutil.copytree(source_framework, candidate, symlinks=True, copy_function=shutil.copy2)
        # An extracted dyld-cache framework may omit its principal Mach-O.
        # Keep every original runtime directory; only the explicitly pinned
        # common-owner principal image may replace a differing original file.
        for name, entry in before.items():
            if name == '.':
                continue
            source = framework / name
            target = candidate / name
            present = target.exists() or target.is_symlink()
            if name == 'Versions/A/Security':
                assert source.is_file() and not source.is_symlink()
                assert not target.is_dir() and not target.is_symlink()
                shutil.copy2(source, target)
            elif present:
                if entry['type'] == 'directory':
                    # Preserve OS directory modes instead of inheriting the
                    # host umask used when preparing the base facade tree.
                    assert source_inventory[name]['type'] == 'directory', name
                else:
                    assert source_inventory[name] == entry, name
            else:
                base_additions.append(name)
                if entry['type'] == 'directory':
                    target.mkdir(mode=entry['mode'])
                elif entry['type'] == 'symlink':
                    target.symlink_to(entry['target'])
                else:
                    shutil.copy2(source, target)
        after = inventory(candidate)
        assert all(after[name] == entry for name, entry in source_inventory.items()
                   if name != 'Versions/A/Security')
        assert all(after[name] == entry for name, entry in before.items()
                   if name != '.' and entry['type'] != 'directory')
        assert inventory(source_framework) == source_inventory
    else:
        shutil.copytree(framework, candidate, symlinks=True, copy_function=shutil.copy2)
        destination = candidate / 'Versions/A/Resources'
        assert not destination.exists() and not destination.is_symlink()
        shutil.copytree(resource, destination, symlinks=True, copy_function=shutil.copy2)
        link = candidate / 'Resources'
        assert not link.exists() and not link.is_symlink()
        link.symlink_to('Versions/Current/Resources')
    destination = candidate / 'Versions/A/Resources'
    assert (candidate / 'Versions/Current').resolve(strict=True) == candidate / 'Versions/A'
    assert (candidate / 'Resources').resolve(strict=True) == destination
    assert (candidate / 'Security').resolve(strict=True) == candidate / 'Versions/A/Security'
    assert inventory(destination) == entries
    assert sha(candidate / 'Versions/A/Security') == sha(binary)
    assert inventory(framework) == before
    report = dict(prepared=True, installed=False, native_execution=False,
        base_build=relative(paths['base_build']), base_build_sha256=sha(paths['base_build']),
        resource_root=relative(resource), source_system_version=relative(system_version),
        source_system_version_sha256=sha(system_version), OS_build=a.expected_os_build,
        bundle_version=bundle_version, framework=relative(candidate),
        binary=relative(candidate / 'Versions/A/Security'), binary_sha256=sha(binary),
        original_image=relative(paths['original_image']), original_image_sha256=sha(paths['original_image']),
        reconstruction_report=relative(paths['reconstruction_report']),
        reconstruction_report_sha256=sha(paths['reconstruction_report']),
        resources=entries, resource_files=sum(v['type']=='file' for v in entries.values()),
        resource_bytes=sum(v.get('size', 0) for v in entries.values()),
        zero_length_source_files=[k for k,v in entries.items() if v['type']=='file' and v['size']==0],
        MDS_databases=db_headers, source_bundle_unchanged=True,
        source_modes_and_symlinks_preserved=True, original_binary_unchanged=True,
        library_dependencies_unchanged=True, no_new_framework_algorithm=True,
        active_indexes_modified=False,
        installation_contract='Select this entire bundle in the unified framework index and mirror the same bundle at canonical /System/Library/Frameworks/Security.framework; do not overlay only two database files.',
        source_cohort_limit='All currently extracted resource entries are preserved, including listed zero-length source entries. This is not independent validation of the original sub-bundle signatures.',
        tool=relative(Path(__file__).resolve()), tool_sha256=sha(Path(__file__)))
    if a.whole_framework:
        images = []
        macho_magic = {bytes.fromhex(value) for value in ('cffaedfe', 'cefaedfe', 'cafebabe', 'cafebabf', 'bebafeca', 'bfbafeca')}
        for name, entry in inventory(candidate).items():
            if entry['type'] != 'file':
                continue
            image = candidate / name
            with image.open('rb') as handle:
                magic = handle.read(4)
            if magic not in macho_magic:
                continue
            commands = []
            for flags in [['llvm-objdump-19', '--macho', '--arch=x86_64', '--dylibs-used'],
                          ['llvm-nm-19', '--arch=x86_64', '--undefined-only', '--just-symbol-name']]:
                command = [*flags, str(image)]
                result = subprocess.run(command, capture_output=True, text=True)
                assert result.returncode == 0, result.stderr
                commands.append(dict(command=command, status=result.returncode, stdout=result.stdout, stderr=result.stderr))
            images.append(dict(path=name, sha256=sha(image), intel_import_audit=commands))
        report.update(whole_framework=True, original_framework=relative(source_framework),
            original_framework_inventory=source_inventory, candidate_inventory=inventory(candidate),
            original_principal_image=source_inventory.get('Versions/A/Security'),
            principal_image_source=relative(binary), principal_image_source_sha256=sha(binary),
            base_added_entries=base_additions, original_runtime_directories_preserved=True,
            runtime_macho_images=images, original_os_bundle_signatures_verified=False,
            source_cohort_limit='Complete extracted OS framework and all runtime directories preserved. Cache-only missing principal image is supplied by the pinned common-owner build; zero-length extracted metadata is preserved. No independent verification of Apple sub-bundle signatures or native loading is claimed.')
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(relative(output / 'build.json'))

if __name__ == '__main__':
    main()
