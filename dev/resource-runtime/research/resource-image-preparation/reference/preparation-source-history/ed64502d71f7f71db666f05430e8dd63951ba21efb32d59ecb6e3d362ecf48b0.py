#!/usr/bin/env python3
"""Pin one original Intel image and optionally run its guarded reconstruction.

Always creates a new target and preserves the previous manifest bytes. The
builder still refuses unknown relocations; this helper does not choose symbols
for missing pointers or claim that a reconstructed image works at runtime.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import runpy
import struct
import subprocess

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
selection = parser.add_mutually_exclusive_group(required=True)
selection.add_argument('--image')
selection.add_argument('--from-target')
parser.add_argument('--exact-import-audit')
parser.add_argument('--target', required=True)
parser.add_argument('--build', action='store_true')
args = parser.parse_args()
assert args.target and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.target)
manifest = root/'config/coregraphics-image-pins.json'
original_manifest = manifest.read_bytes()
pins = json.loads(original_manifest)
assert args.target not in pins
if args.from_target:
    assert args.exact_import_audit and args.from_target in pins
    args.image = pins[args.from_target]['path']
else:
    assert not args.exact_import_audit
assert args.image.startswith('/') and '..' not in Path(args.image).parts
folder = root/('runtime/rebuilt-'+args.target)
report_path = root/('artifacts/'+args.target+'-input.json')
assert not folder.exists() and not report_path.exists()
ns = runpy.run_path(str(root/'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root/'runtime/fullsystem-libraries'})
image = ns['image'](args.image)
source = root/'runtime/fullsystem-libraries'/args.image.lstrip('/')
data = source.read_bytes()
assert data[:4] == bytes.fromhex('cffaedfe') and struct.unpack_from('<I', data, 4)[0] == 0x01000007
digest = lambda data: hashlib.sha256(data).hexdigest()
classes = sum(size//8 for name, segment, address, size, flags in image.sections if name == '__objc_classlist')
assert all(size % 8 == 0 for name, _, _, size, _ in image.sections if name == '__objc_classlist')
swift = any(name.startswith('__swift') for name, _, _, _, _ in image.sections)
pin = dict(path=args.image, sha256=digest(data), reference_set='fullsystem',
    objc_classes=classes, import_providers={})
for section, key in [('__objc_catlist', 'restore_objc_categories'),
                     ('__objc_protolist', 'restore_objc_protocols')]:
    if not classes and any(name == section and size for name, _, _, size, _ in image.sections):
        pin[key] = True
if args.from_target:
    pin = copy.deepcopy(pins[args.from_target])
    assert pin['sha256'] == digest(data)
    audit_path = root/args.exact_import_audit
    audit = json.loads(audit_path.read_text())
    missing_path = root/('runtime/rebuilt-'+args.from_target+'/missing-cache-imports.json')
    missing = json.loads(missing_path.read_text())
    assert missing['diagnostic_only'] and not missing['image_emitted']
    assert audit['target'] == args.from_target and audit['unresolved'] == 0
    assert audit['original_image_sha256'] == pin['sha256']
    assert audit['missing_imports_sha256'] == digest(missing_path.read_bytes())
    assert [(row['target'], row['slots']) for row in audit['rows']] == [
        (row['target'], row['slots']) for row in missing['imports']]
    wanted = {int(row['target'], 16) for row in audit['rows']}
    exact = {address: [] for address in wanted}
    for provider in image.dependencies:
        original = root/'runtime/fullsystem-libraries'/provider.lstrip('/')
        assert digest(original.read_bytes()) == audit['original_dependency_sha256'][provider]
        for symbol, value in ns['image'](provider).exports.items():
            if value[0] == 'address' and value[1] in wanted:
                exact[value[1]].append([symbol, provider])
    additions = pin.setdefault('cache_imports', {})
    for row in audit['rows']:
        choices = exact[int(row['target'], 16)]
        # Folded unrelated symbols and special aliases need manual typed
        # review. This mode accepts only one exact original public identity.
        assert len(choices) == 1 and choices == row['exports'] and choices[0] == row['selected']
        symbol, provider = choices[0]
        assert ns['resolve'](provider, symbol) == int(row['target'], 16)
        assert additions.get(symbol, provider) == provider
        additions[symbol] = provider
old_sha = digest(original_manifest)
snapshot = root/'runtime/source-input-history'/old_sha
if snapshot.exists(): assert snapshot.read_bytes() == original_manifest
else: snapshot.write_bytes(original_manifest)
history_path = root/'runtime/source-input-history/manifest.json'
history = json.loads(history_path.read_text())
name = str(manifest.relative_to(root))
previous = history.get(name, {})
revisions = dict(previous.get('revisions', {}))
if 'sha256' in previous: revisions[previous['sha256']] = previous['snapshot']
history[name] = dict(sha256=old_sha, snapshot=str(snapshot.relative_to(root)), revisions=revisions)
history_path.write_text(json.dumps(history, indent=2)+'\n')
pins[args.target] = pin
manifest.write_text(json.dumps(pins, indent=2)+'\n')
command = ['python3', 'scripts/rebuild-c-cache-image.py', '--target-manifest', str(manifest.relative_to(root)),
    '--target', args.target, '--lazy-functions', '--collect-missing-imports']
command += ['--experimental-swift', '--repair-swift-relative'] if swift else ['--analyze-code']
record = dict(target=args.target, pin=pin, original_bytes=len(data), swift_metadata=swift,
    original_dependencies=image.dependencies, previous_manifest_sha256=old_sha,
    manifest_sha256=digest(manifest.read_bytes()), command=command,
    preparation_source_sha256=digest(Path(__file__).read_bytes()),
    reconstruction_attempted=False, image_runtime_verified=False)
if args.from_target:
    record.update(parent_target=args.from_target, exact_import_audit=args.exact_import_audit,
        exact_import_audit_sha256=digest(audit_path.read_bytes()))
report_path.write_text(json.dumps(record, indent=2)+'\n')
status = 0
if args.build:
    log = root/('logs/'+args.target+'-build.log')
    assert not log.exists()
    with log.open('w') as out:
        result = subprocess.run(command, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    status = result.returncode
    record.update(reconstruction_attempted=True, build_returncode=status,
        log=str(log.relative_to(root)), log_sha256=digest(log.read_bytes()))
    report_path.write_text(json.dumps(record, indent=2)+'\n')
print('EVIDENCE', report_path.relative_to(root))
raise SystemExit(status)
