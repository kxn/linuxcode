#!/usr/bin/env python3
"""Extend an immutable graphics experiment with a pinned reconstructed image.

This only creates a separate stage. It neither installs binaries nor claims
that a successfully reconstructed library has passed runtime validation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shutil

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent', required=True)
parser.add_argument('--tag', required=True)
parser.add_argument('--target', action='append', required=True)
args = parser.parse_args()
assert args.tag and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.tag)
sha = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
resolve = runpy.run_path(str(root / 'scripts/resolve-evidence-history.py'))['resolve']
parent = json.loads((root / args.parent).read_text())
for path, expected in parent['files'].items():
    if path.startswith(('scripts/', 'config/', 'vendor/')):
        resolve(path, expected)
    else:
        assert sha(path) == expected, path
for path, target in parent.get('links', {}).items():
    assert os.readlink(root / path) == target, path
manifest = 'config/coregraphics-image-pins.json'
pins = json.loads((root / manifest).read_text())
assert len(args.target) == len(set(args.target))
components = []
tlv_sources = []
for target in args.target:
    pin = pins[target]
    name = Path(pin['path']).name
    source = 'runtime/rebuilt-' + target + '/' + name
    reconstruction = 'runtime/rebuilt-' + target + '/reconstruction.json'
    report = json.loads((root / reconstruction).read_text())
    original = 'runtime/fullsystem-libraries' + pin['path']
    assert sha(original) == pin['sha256'] == report['original_image_sha256']
    assert sha(source) == report['staged_image_sha256']
    assert not report['installed'] and not report['execution_verified']
    assert not report['backend_call_overrides']
    if report.get('dysymtab_alias_repair'):
        proof=report['dysymtab_alias_repair']
        resolve(proof['source'],proof['source_sha256'])
        tlv_sources.append(proof['source'])
    for path,digest in report.get('swift_metadata',{}).get('singleton_objc_source_sha256',{}).items():
        tlv_sources.append(str(resolve(path,digest)))
    if report.get('optimized_tlv_restoration'):
        preparation = 'artifacts/'+target+'-input.json'
        prepared = json.loads((root/preparation).read_text())
        validator = 'scripts/cache-tlv-optimization.py'
        assert prepared['TLV_validator_sha256'] == sha(validator)
        assert prepared['original_cache_TLV_optimizations'] == report['optimized_tlv_restoration']
        tlv_sources += [validator, preparation]
    if report.get('original_absent_weak_dependencies'):
        proof = report['original_absent_weak_dependencies']
        assert proof['original_image_sha256'] == pin['sha256']
        for weak in proof['dependencies']:
            provider = weak['provider']
            assert weak['load_command'] == '0x80000018' and weak['original_provider_absent']
            for prefix in ['runtime/fullsystem-libraries','runtime/rootfs/usr/libexec/darling','runtime/state/prefix']:
                assert not (root/prefix/provider.lstrip('/')).exists(), provider
            assert not any(Path(path).name == Path(provider).name for path in parent['files']), provider
    components.append(dict(target=target, name=name, source=source,
                           reconstruction=reconstruction, original=original, install_name=pin['path']))
assert len({item['name'] for item in components}) == len(components)
folder = root / ('runtime/coregraphics-native-' + args.tag)
output = root / ('artifacts/coregraphics-native-' + args.tag + '-stage.json')
assert not folder.exists() and not output.exists()
old_folder = Path(parent['library']).parents[4]
assert str(old_folder).startswith('runtime/coregraphics-native-')

def relative_destination(item):
    path = item['install_name']
    if path.count('.framework/') > 1:
        # Preserve the original embedded framework tree. Classic dyld searches
        # the innermost framework suffix; the resource overlay separately adds
        # this framework's parent directory to its scoped search paths.
        outer, suffix = path.split('.framework/', 1)
        return Path('frameworks')/(Path(outer).name+'.framework')/suffix
    name = item['name']
    if name.endswith('.dylib'):
        return Path('libraries')/name
    outer,suffix=path.split('.framework/',1)
    return Path('frameworks')/(Path(outer).name+'.framework')/suffix

for item in components:
    relative = relative_destination(item)
    assert not (root/old_folder/relative).exists()
    for previous in parent['dependencies']:
        if previous['target'] == item['target']:
            assert previous['source'] == item['source'] and previous['reconstruction'] == item['reconstruction']
shutil.copytree(root / old_folder, folder, symlinks=True)
for item in components:
    name = item['name']
    destination = folder/relative_destination(item)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / item['source'], destination)
    if not name.endswith('.dylib'):
        if destination.parent.parent.name=='Versions':
            framework = destination.parents[2]
            assert framework.name==name+'.framework'
            (framework / 'Versions/Current').symlink_to(destination.parent.name)
            (framework / name).symlink_to('Versions/Current/' + name)
        else:
            assert destination.parent.name==name+'.framework'
record = {**parent, 'library': str((folder / Path(parent['library']).relative_to(old_folder)).relative_to(root)),
    'installed': False, 'runtime_execution_verified': False, 'resource_compilation_verified': False,
    'parent_stage': args.parent, 'parent_stage_sha256': sha(args.parent),
    'dependencies': [*parent['dependencies'], *[dict(target=item['target'], source=item['source'],
        reconstruction=item['reconstruction']) for item in components
        if item['target'] not in {row['target'] for row in parent['dependencies']}]], 'files': dict(parent['files'])}
record['added_install_paths'] = [dict(target=item['target'], install_name=item['install_name'],
    destination=str((folder/relative_destination(item)).relative_to(root))) for item in components]
record['files'].update({p: sha(p) for p in [args.parent, manifest,
    *[item[key] for item in components for key in ['source', 'original', 'reconstruction']],
    'scripts/extend-coregraphics-stage.py', 'scripts/rebuild-c-cache-image.py',
    'scripts/cache-patch-metadata.py', 'config/cache-patch-metadata-format.json', *tlv_sources]})
record['files'].update({str(p.relative_to(root)): sha(str(p.relative_to(root)))
    for p in folder.rglob('*') if p.is_file() and not p.is_symlink()})
record['links'] = {**parent.get('links', {}), **{str(p.relative_to(root)): os.readlink(p)
    for p in folder.rglob('*') if p.is_symlink()}}
output.write_text(json.dumps(record, indent=2) + '\n')
print(output.relative_to(root))
