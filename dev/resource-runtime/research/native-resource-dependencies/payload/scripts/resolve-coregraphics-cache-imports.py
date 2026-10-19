#!/usr/bin/env python3
"""Audit exact dependency exports for the pinned CoreGraphics/font experiments."""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import json
import runpy

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', required=True)
parser.add_argument('--report', required=True)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
manifest = root / 'config/coregraphics-image-pins.json'
config = json.loads(manifest.read_text())
pin = config[args.target]
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(root / ('runtime/fullsystem-libraries' + pin['path'])) == pin['sha256']
cache = runpy.run_path(str(root / 'scripts/dsc-image.py'), init_globals={
    'REFERENCE_CACHE_PATH': root / 'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT': root / 'runtime/fullsystem-libraries'})
image = cache['image'](pin['path'])
missing = root / ('runtime/rebuilt-' + args.target + '/missing-cache-imports.json')
data = json.loads(missing.read_text())
assert data['diagnostic_only'] and not data['image_emitted']
wanted = {int(row['target'], 16) for row in data['imports']}
exports = defaultdict(list)
providers = {}
for provider in image.dependencies:
    providers[provider] = digest(root / ('runtime/fullsystem-libraries' + provider))
    for symbol, value in cache['image'](provider).exports.items():
        if value[0] == 'address' and value[1] in wanted:
            exports[value[1]].append((symbol, provider))
rows, imports = [], {}
for row in data['imports']:
    choices = exports[int(row['target'], 16)]
    selected = choices[0] if len(choices) == 1 else None
    # These are the Swift metadata and ObjC Class names of the same class,
    # rather than unrelated functions folded to an identical body.
    class_alias = {symbol for symbol, provider in choices} == {
        '_$ss20__StaticArrayStorageCN', '_OBJC_CLASS_$__TtCs20__StaticArrayStorage'}
    if class_alias and {provider for symbol, provider in choices} == {'/usr/lib/swift/libswiftCore.dylib'}:
        selected = next(choice for choice in choices if choice[0] == '_$ss20__StaticArrayStorageCN')
    if selected:
        assert cache['resolve'](selected[1], selected[0]) == int(row['target'], 16)
        imports[selected[0]] = selected[1]
    rows.append({**row, 'exports': choices, 'selected': selected, 'same_class_alias': class_alias})
report = root / args.report
assert not report.exists()
record = dict(target=args.target, original_image_sha256=pin['sha256'],
              missing_imports_sha256=digest(missing), original_dependency_sha256=providers,
              unresolved=sum(row['selected'] is None for row in rows), rows=rows,
              runtime_verified=False, applied=False)
if args.apply:
    assert record['unresolved'] == 0, 'Review unresolved/ambiguous imports before pinning'
    history_path = root / 'runtime/source-input-history/manifest.json'
    history = json.loads(history_path.read_text())
    previous_hash = digest(manifest)
    snapshot = 'runtime/source-input-history/' + previous_hash
    (root / snapshot).write_bytes(manifest.read_bytes())
    entry = history.setdefault('config/coregraphics-image-pins.json', dict(sha256=previous_hash, snapshot=snapshot))
    entry.setdefault('revisions', {})[previous_hash] = snapshot
    history_path.write_text(json.dumps(history, indent=2) + '\n')
    existing = pin.setdefault('cache_imports', {})
    for symbol, provider in imports.items():
        assert existing.get(symbol, provider) == provider
    existing.update(imports)
    manifest.write_text(json.dumps(config, indent=2) + '\n')
    record.update(applied=True, manifest_sha256=digest(manifest))
report.write_text(json.dumps(record, indent=2) + '\n')
print(args.target, 'resolved:', len(imports), 'unresolved:', record['unresolved'])
